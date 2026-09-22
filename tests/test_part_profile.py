import io
import json
import unittest
import uuid
from unittest.mock import patch

from PIL import Image
from app import app, connect
from part_profile import validate_profile, parse_suggestions
from search import prompt_for


class ProfileTests(unittest.TestCase):
    def test_reference_and_quantity(self):
        result = validate_profile({'facts': [{'field': 'references', 'value': '001 234 A'}, {'field': 'quantity', 'value': '2'}]})
        self.assertEqual(result['facts'][0]['value'], '001 234 A')
        for quantity in ('0', '-1', '1.5', '1000'):
            with self.assertRaises(ValueError):
                validate_profile({'facts': [{'field': 'quantity', 'value': quantity}]})

    def test_ai_cannot_confirm_or_set_preferences(self):
        data = {'suggestions': [{'field': 'aliases', 'value': 'Feu arrière', 'verification_status': 'user_confirmed'}]}
        result = parse_suggestions(json.dumps(data), uuid.uuid4())
        self.assertEqual(result['suggestions'][0]['verification_status'], 'unverified')
        self.assertEqual(result['suggestions'][0]['review_status'], 'pending')
        data['suggestions'][0]['field'] = 'quantity'
        with self.assertRaises(ValueError):
            parse_suggestions(json.dumps(data), uuid.uuid4())

    def test_invalid_ai_never_applies(self):
        for raw in ('not json', '[]', '{"suggestions":{}}', '{"suggestions":[{"field":"references","value":"x","evidence":[{"url":"javascript:alert(1)"}]}]}'):
            with self.assertRaises(ValueError):
                parse_suggestions(raw, uuid.uuid4())

    def test_malformed_fields_and_statuses_are_validation_errors(self):
        for fact in ({'field': [], 'value': 'x'}, {'field': 'name', 'value': 'x', 'review_status': []}):
            with self.assertRaises(ValueError):
                validate_profile({'facts': [fact]})

    def test_prompt_includes_leads_as_unverified(self):
        profile = validate_profile({'facts': [{'field': 'compatible_vehicles', 'value': 'Possible model X'}]})
        prompt = json.loads(prompt_for(dict(vehicle='R19', description='Tail lamp', instructions='', part_profile=profile)))
        self.assertEqual(prompt['part_profile'], profile)
        self.assertIn('never proof', prompt['part_profile_rules'])


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        self.tx = self.conn.transaction(force_rollback=True)
        self.tx.__enter__()
        conn = self.conn
        class Shared:
            def __enter__(self): return conn
            def __exit__(self, *args): return False
        self.shared = Shared()
        self.mock = patch('app.connect', return_value=self.shared)
        self.mock.start()
        self.client = app.test_client()
        self.client.get('/requests/new')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']

    def tearDown(self):
        self.mock.stop()
        self.tx.__exit__(None, None, None)
        self.conn.close()

    def create(self, **extra):
        data = dict(csrf=self.csrf, description='Rare left rear tail lamp', vehicle='Renault 19', part_profile='{}')
        data.update(extra)
        response = self.client.post('/part-drafts', data=data)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.json

    def test_session_isolation_and_csrf(self):
        draft = self.create()
        other = app.test_client()
        self.assertEqual(other.get('/part-drafts/' + draft['id']).status_code, 404)
        self.assertEqual(self.client.post('/part-drafts', data={'description': 'A rear tail lamp'}).status_code, 400)

    def test_photos_recover_commit_once(self):
        photo = io.BytesIO()
        Image.new('RGB', (15, 20)).save(photo, 'PNG'); photo.seek(0)
        draft = self.create(photos=(photo, 'photo.png'))
        recovered = self.client.get('/part-drafts/' + draft['id']).json
        self.assertEqual(len(recovered['photos']), 1)
        self.assertEqual(self.client.get(recovered['photos'][0]['url']).mimetype, 'image/jpeg')
        data = dict(csrf=self.csrf, revision=draft['revision'])
        first = self.client.post('/part-drafts/' + draft['id'] + '/commit', data=data)
        second = self.client.post('/part-drafts/' + draft['id'] + '/commit', data=data)
        self.assertEqual(first.status_code, 200, first.get_data(as_text=True))
        self.assertEqual(first.json, second.json)
        self.assertEqual(self.client.get(first.json['url']).status_code, 200)

    def test_revision_and_pending_proposals(self):
        fact = {'field': 'references', 'value': 'Maybe 001', 'origin': 'ai', 'review_status': 'pending'}
        draft = self.create(part_profile=json.dumps({'facts': [fact]}))
        path = '/part-drafts/' + draft['id']
        self.assertEqual(self.client.post(path + '/commit', data=dict(csrf=self.csrf, revision=draft['revision'])).status_code, 422)
        self.assertEqual(self.client.post(path + '/update', data=dict(csrf=self.csrf, revision=999)).status_code, 409)
        fact['review_status'] = 'accepted'
        updated = self.client.post(path + '/review', data=dict(csrf=self.csrf, revision=draft['revision'], description='Rare left rear tail lamp', vehicle='Renault 19', part_profile=json.dumps({'facts': [fact]})))
        self.assertEqual(updated.status_code, 200)
        saved = self.client.post(path + '/commit', data=dict(csrf=self.csrf, revision=updated.json['revision']))
        self.assertEqual(saved.status_code, 200)
        self.assertIn(b'Unverified', self.client.get(saved.json['url']).data)

    def test_enqueue_idempotency_and_cancellation(self):
        draft = self.create()
        path = '/part-drafts/' + draft['id']
        data = dict(csrf=self.csrf, revision=draft['revision'], model='codex:', idempotency_key=str(uuid.uuid4()))
        first = self.client.post(path + '/enrichments', data=data)
        second = self.client.post(path + '/enrichments', data=data)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json, second.json)
        self.assertEqual(self.client.post(path + '/commit', data=dict(csrf=self.csrf, revision=draft['revision'])).status_code, 409)
        self.assertEqual(self.client.post(path + '/enrichments/' + first.json['id'] + '/cancel', data=dict(csrf=self.csrf)).status_code, 200)
        self.assertEqual(self.client.get(path + '/enrichments/' + first.json['id']).json['status'], 'cancelled')

    def test_worker_validates_output_and_respects_cancel(self):
        from enrichment_worker import process_job
        draft = self.create()
        path = '/part-drafts/' + draft['id']
        response = self.client.post(path + '/enrichments', data=dict(csrf=self.csrf, revision=draft['revision'], model='codex:', idempotency_key=str(uuid.uuid4())))
        run_id = response.json['id']
        job = self.conn.execute("UPDATE part_enrichments SET status='running' WHERE id=%s RETURNING *", (run_id,)).fetchone()
        output = json.dumps({'suggestions': [{'field': 'aliases', 'value': 'Feu arrière gauche (French)', 'reason': 'Search synonym', 'evidence': []}]})
        with patch('enrichment_worker.connect', return_value=self.shared), patch('enrichment_worker.run_codex', return_value={'result': output}) as transport:
            process_job(job)
            self.assertEqual(transport.call_count, 1)
        result = self.client.get(path + '/enrichments/' + run_id).json
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['output']['suggestions'][0]['verification_status'], 'unverified')
        self.conn.execute("UPDATE part_enrichments SET status='cancelled' WHERE id=%s", (run_id,))
        with patch('enrichment_worker.connect', return_value=self.shared), patch('enrichment_worker.run_codex', return_value={'result': output}):
            process_job(job)
        self.assertEqual(self.client.get(path + '/enrichments/' + run_id).json['status'], 'cancelled')

    def test_identifier_research_uses_web_tools_and_saves_evidence(self):
        from enrichment_worker import process_job
        from test_languages_identifiers import reference
        draft = self.create()
        path = '/part-drafts/' + draft['id']
        response = self.client.post(path + '/enrichments', data=dict(csrf=self.csrf, revision=draft['revision'], model='codex:', purpose='identifiers', idempotency_key=str(uuid.uuid4())))
        run_id = response.json['id']
        job = self.conn.execute("UPDATE part_enrichments SET status='running',provider='openwebui',model='local-model' WHERE id=%s RETURNING *", (run_id,)).fetchone()
        output = {'result':json.dumps({'suggestions':[reference()]}), 'web_search_observed':True, 'sources':['https://example.com/catalogue/00123']}
        with patch('enrichment_worker.connect', return_value=self.shared), patch('enrichment_worker.run_openwebui', return_value=output) as research, patch('enrichment_worker.run_openwebui_profile') as memory_fill:
            process_job(job)
            self.assertTrue(research.call_args.kwargs['require_web'])
            self.assertIn('Research identifiers only', research.call_args.kwargs['system_prompt'])
            memory_fill.assert_not_called()
        result = self.client.get(path + '/enrichments/' + run_id).json
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['output']['suggestions'][0]['identifier']['code'], '00123-AB')
        self.assertEqual(result['output']['suggestions'][0]['verification_status'], 'unverified')

    def test_language_settings_and_enrichment_snapshot(self):
        from language_settings import get_preferences
        self.assertEqual(self.client.get('/settings').status_code, 200)
        self.assertEqual(self.client.post('/settings', data={'csrf':self.csrf,'response_language':'pt'}).status_code, 400)
        response = self.client.post('/settings', data={'csrf':self.csrf,'response_language':'pt','search_languages':['fr','de']})
        self.assertEqual(response.status_code, 303)
        draft = self.create()
        run = self.client.post('/part-drafts/' + draft['id'] + '/enrichments', data=dict(csrf=self.csrf, revision=draft['revision'], model='codex:', purpose='identifiers', idempotency_key=str(uuid.uuid4())))
        self.assertEqual(run.status_code, 202)
        job = self.conn.execute('SELECT * FROM part_enrichments WHERE id=%s', (run.json['id'],)).fetchone()
        self.assertEqual(job['purpose'], 'identifiers')
        self.assertEqual(job['input']['language_preferences'], {'response_language':'pt','search_languages':['fr','de']})
        self.client.post('/settings', data={'csrf':self.csrf,'response_language':'es','search_languages':['en']})
        snapshot = self.conn.execute('SELECT input FROM part_enrichments WHERE id=%s', (run.json['id'],)).fetchone()['input']
        self.assertEqual(snapshot['language_preferences']['response_language'], 'pt')

    def test_discord_locks_do_not_block_enrichment_or_generation(self):
        from worker_locks import DISCORD_WORKER, DISCORD_SETTINGS, ENRICHMENT_WORKER, AI_GENERATION
        with connect() as discord, connect() as enrichment:
            discord.execute('SELECT pg_advisory_lock(%s)', (DISCORD_WORKER,))
            discord.execute('SELECT pg_advisory_lock(%s)', (DISCORD_SETTINGS,))
            try:
                for lock_id in (ENRICHMENT_WORKER, AI_GENERATION):
                    acquired = enrichment.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (lock_id,)).fetchone()['acquired']
                    self.assertTrue(acquired)
                    enrichment.execute('SELECT pg_advisory_unlock(%s)', (lock_id,))
            finally:
                discord.execute('SELECT pg_advisory_unlock(%s)', (DISCORD_WORKER,))
                discord.execute('SELECT pg_advisory_unlock(%s)', (DISCORD_SETTINGS,))

    def test_profile_snapshots_manual_and_scheduled(self):
        from scheduling import enqueue_search
        from psycopg.types.json import Jsonb
        profile = validate_profile({'facts': [{'field': 'aliases', 'value': 'Feu arrière gauche'}]})
        draft = self.create(part_profile=json.dumps(profile))
        response = self.client.post('/part-drafts/' + draft['id'] + '/commit', data=dict(csrf=self.csrf, revision=draft['revision']))
        order_id = response.json['url'].rsplit('/', 1)[-1]
        order = self.conn.execute('SELECT * FROM requests WHERE id=%s', (order_id,)).fetchone()
        settings = dict(provider='codex', model='', instructions='', preferred_price='', pickup_areas='', shipping_areas='', reasoning_effort='', preferred_options=6, priority_websites=[])
        for schedule_id in (None, uuid.uuid4()):
            run_id = enqueue_search(self.conn, order, settings, schedule_id)
            snapshot = self.conn.execute('SELECT part_profile FROM searches WHERE id=%s', (run_id,)).fetchone()['part_profile']
            self.assertEqual(snapshot, profile)
            languages = self.conn.execute('SELECT language_preferences FROM searches WHERE id=%s', (run_id,)).fetchone()['language_preferences']
            self.assertEqual(languages['search_languages'], ['en','pt','fr','de','es'])
            self.conn.execute("UPDATE searches SET status='completed' WHERE id=%s", (run_id,))
        self.conn.execute('UPDATE requests SET part_profile=%s WHERE id=%s', (Jsonb({}), order_id))
        self.assertEqual(self.conn.execute('SELECT part_profile FROM searches WHERE id=%s', (run_id,)).fetchone()['part_profile'], profile)
        self.assertIn(b'Part details used in this search', self.client.get(response.json['url']).data)

    def test_manual_profile_and_edit_conflict(self):
        response = self.client.post('/requests', data=dict(csrf=self.csrf, description='Rare left rear tail lamp', part_references='001 23'))
        self.assertEqual(response.status_code, 303)
        request_id = response.location.rsplit('/', 1)[1]
        row = self.conn.execute('SELECT * FROM requests WHERE id=%s', (request_id,)).fetchone()
        self.assertEqual(row['part_profile']['facts'][0]['value'], '001 23')
        draft = self.create(request_id=request_id, profile_revision='0')
        self.conn.execute('UPDATE requests SET profile_revision=profile_revision+1 WHERE id=%s', (request_id,))
        response = self.client.post('/part-drafts/' + draft['id'] + '/commit', data=dict(csrf=self.csrf, revision=draft['revision']))
        self.assertEqual(response.status_code, 409)


if __name__ == '__main__':
    unittest.main()
