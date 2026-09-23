from page_payload import page_data
import io
import json
from pathlib import Path
import unittest
from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch

import httpx
from PIL import Image
from psycopg.types.json import Jsonb

from app import app, connect, render_markdown
from search import run_codex, run_openwebui, source_links, prompt_for, SYSTEM_PROMPT
from worker import claim_job, process_job
from listings import parse_research, public_url, listing_key
from scheduling import dispatch_due, next_occurrence


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        self.transaction = self.conn.transaction(force_rollback=True)
        self.transaction.__enter__()

        class SharedConnection:
            def __enter__(_self):
                return self.conn

            def __exit__(_self, *args):
                return False

        self.patches = [patch('app.connect', return_value=SharedConnection()),
                        patch('worker.connect', return_value=SharedConnection()),
                        patch('search.check_codex', return_value='Authenticated')]
        for item in self.patches:
            item.start()
        self.client = app.test_client()
        self.client.get('/requests/new')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']
        image = io.BytesIO()
        Image.new('RGB', (20, 20), 'blue').save(image, 'PNG')
        image.seek(0)
        response = self.client.post('/requests', data={'csrf': self.csrf,
            'description': 'Left rear light for a Renault 19', 'vehicle': 'Renault 19, 1994',
            'photos': (image, 'part.png')})
        self.order_id = response.location.rsplit('/', 1)[-1]
        self.url = f'/requests/{self.order_id}/search'

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.transaction.__exit__(None, None, None)
        self.conn.close()

    def enqueue(self, **overrides):
        data = {'csrf': self.csrf, 'model': 'codex', 'instructions': 'Used parts in Portugal, under EUR 150.'}
        data.update(overrides)
        return self.client.post(self.url, data=data)

    def job(self):
        return self.conn.execute('SELECT * FROM searches WHERE request_id=%s', (self.order_id,)).fetchone()

    def test_queue_snapshots_photos_and_prevents_duplicate_search(self):
        self.assertEqual(self.enqueue().status_code, 303)
        job = self.job()
        self.assertEqual(job['status'], 'queued')
        self.assertEqual(self.enqueue().status_code, 303)
        count = self.conn.execute('SELECT count(*) AS n FROM searches WHERE request_id=%s', (self.order_id,)).fetchone()['n']
        self.assertEqual(count, 1)
        self.conn.execute('UPDATE requests SET description=%s WHERE id=%s', ('Changed description after queueing', self.order_id))
        self.conn.execute('DELETE FROM photos WHERE request_id=%s', (self.order_id,))
        self.assertEqual(self.job()['description'], 'Left rear light for a Renault 19')
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM search_photos WHERE search_id=%s', (job['id'],)).fetchone()['n'], 1)

    def test_queue_validation(self):
        self.assertEqual(self.enqueue(csrf='bad').status_code, 400)
        self.assertEqual(self.enqueue(model='other').status_code, 400)
        self.assertEqual(self.enqueue(instructions='x' * 4001).status_code, 400)
        self.assertEqual(self.enqueue(model='openwebui:missing-model').status_code, 400)
        self.conn.execute("UPDATE ai_connections SET models=%s, api_key='configured' WHERE provider='openwebui'", (Jsonb(['vision-model']),))
        self.assertEqual(self.enqueue(model='openwebui:vision-model').status_code, 303)
        self.assertEqual(self.job()['model'], 'vision-model')

    def test_preferences_and_codex_model_are_saved_and_displayed(self):
        self.assertEqual(self.enqueue(codex_model='test-model', preferred_price='€150',
            pickup_areas='Northern Portugal / Galicia', shipping_areas='Europe').status_code, 303)
        job = self.job()
        self.assertEqual(job['model'], 'test-model')
        payload = json.loads(prompt_for(job))
        self.assertEqual(payload['preferred_price_not_a_limit'], '€150')
        self.assertEqual(payload['pickup_areas'], 'Northern Portugal / Galicia')
        self.assertEqual(payload['shipping_seller_areas'], 'Europe')
        self.assertIn('never a maximum', SYSTEM_PROMPT)
        page = self.client.get(f'/requests/{self.order_id}').get_data(as_text=True)
        for key, value in {'model': 'test-model', 'preferred_price': '€150', 'pickup_areas': 'Northern Portugal / Galicia', 'shipping_areas': 'Europe'}.items():
            self.assertEqual(page_data(page)['searches'][0][key], value)

    def test_preference_and_model_validation(self):
        for values in ({'preferred_price': 'x' * 81}, {'pickup_areas': 'x' * 501},
                       {'shipping_areas': 'x' * 501}, {'codex_model': '--bad model'}):
            self.assertEqual(self.enqueue(**values).status_code, 400)
        self.assertIsNone(self.job())

    def test_reasoning_effort_validation_and_history(self):
        with patch('search.cached_codex_models', return_value={'test-model': ['low', 'high']}):
            self.assertEqual(self.enqueue(codex_model='test-model', reasoning_effort='ultra').status_code, 400)
            self.assertEqual(self.enqueue(reasoning_effort='high').status_code, 400)
            self.assertEqual(self.enqueue(codex_model='test-model', reasoning_effort='high').status_code, 303)
        self.assertEqual(self.job()['reasoning_effort'], 'high')
        page = self.client.get(f'/requests/{self.order_id}').get_data(as_text=True)
        self.assertEqual(page_data(page)['searches'][0]['reasoning_effort'], 'high')

    def test_worker_saves_result_and_safe_rendering(self):
        self.enqueue()
        # Isolate claim order from any existing user searches.
        self.conn.execute("UPDATE searches SET created_at='2000-01-01' WHERE request_id=%s", (self.order_id,))
        job = claim_job()
        self.assertEqual(str(job['request_id']), self.order_id)
        self.assertEqual(self.job()['status'], 'running')
        with patch('worker.run_codex', return_value={'result': '<script>alert(1)</script> Part found: https://example.com/part',
                   'sources': ['https://example.com/part'], 'web_search_observed': True}) as run:
            process_job(job)
        self.assertEqual(len(run.call_args.args[1]), 1)
        self.assertEqual(self.job()['status'], 'completed')
        response = self.client.get(f'/requests/{self.order_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'\\u003cscript\\u003e', response.data)
        self.assertNotIn(b'<script>alert', response.data)
        self.assertIn(b'https://example.com/part', response.data)

    def test_worker_failure_is_saved(self):
        self.enqueue()
        with patch('worker.run_codex', side_effect=ValueError('Codex login required.')):
            process_job(self.job())
        self.assertEqual(self.job()['status'], 'failed')
        self.assertEqual(self.job()['error'], 'Codex login required.')
        self.assertIsNotNone(self.job()['finished_at'])

    def test_openwebui_native_research_includes_images_and_web_search(self):
        self.enqueue()
        job = dict(self.job(), model='vision-model')
        calls = []
        tree = {}
        task_states = iter([['test-task'], ['test-task'], []])

        def respond(method, path, **kwargs):
            calls.append((method, path, kwargs))
            if path == 'api/config':
                data = {'features': {'enable_web_search': True}}
            elif path == 'api/v1/chats/new':
                tree.update(kwargs['json']['chat']['history'])
                data = {'id': 'test-chat'}
            elif path == 'api/chat/completions':
                data = {'task_ids': ['test-task']}
            elif path.startswith('api/tasks/chat/'):
                data = {'task_ids': next(task_states)}
            else:
                data = {'chat': {'history': {'messages': {tree['currentId']: {
                    'content': 'Found a matching part.', 'done': True,
                    'sources': [{'metadata': [{'source': 'https://example.com/listing'}]}]}}}}}
            return httpx.Response(200, json=data)

        with patch('search.check_openwebui', return_value=['vision-model']), patch('search.cipher') as encryption, patch('search.httpx.Client') as client, patch('search.time.sleep') as sleep, patch('search.time.monotonic', return_value=0):
            encryption.return_value.decrypt.return_value = b'test-key'
            client.return_value.__enter__.return_value.request.side_effect = respond
            remote = []
            result = run_openwebui(job, [{'data': b'jpeg-test'}],
                                  {'base_url': 'https://openwebui.test', 'api_key': 'encrypted'}, remote.append)
        self.assertEqual(remote, ['https://openwebui.test/c/test-chat'])
        self.assertEqual(sleep.call_count, 2)
        self.assertFalse(any('/stop/' in path for _, path, _ in calls))
        body = next(kwargs['json'] for _, path, kwargs in calls if path == 'api/chat/completions')
        self.assertTrue(body['stream'])
        self.assertTrue(body['features']['web_search'])
        self.assertEqual(body['params']['function_calling'], 'native')
        self.assertTrue(body['session_id'])
        self.assertTrue(body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,'))
        self.assertIn(job['instructions'], body['messages'][1]['content'][0]['text'])
        self.assertTrue(result['web_search_observed'])
        self.assertEqual(result['sources'], ['https://example.com/listing'])

    def test_codex_images_live_search_and_restricted_environment(self):
        self.enqueue(codex_model='test-model', preferred_price='EUR 150', shipping_areas='Europe')
        seen = {}

        class FakeProcess:
            returncode = 0

            def __init__(_self, command, **kwargs):
                seen.update(command=command, kwargs=kwargs)
                Path(command[command.index('--output-last-message') + 1]).write_text('Found a part.')
                kwargs['stdout'].write(b'{"item":{"type":"web_search","url":"https://example.com"}}\n')
                kwargs['stdout'].write(b'{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":50}}\n')
                seen['schema'] = json.loads(Path(command[command.index('--output-schema') + 1]).read_text())

            def communicate(_self, content, timeout):
                seen['prompt'] = content
                seen['timeout'] = timeout

        with patch('search.subprocess.Popen', FakeProcess):
            result = run_codex(dict(self.job(), reasoning_effort='high'), [{'data': b'jpeg-test'}])
        self.assertIn('model_reasoning_effort="high"', seen['command'])
        self.assertEqual(seen['timeout'], 600)
        self.assertIn('web_search="live"', seen['command'])
        self.assertIn('--image', seen['command'])
        self.assertEqual(seen['command'][seen['command'].index('--model') + 1], 'test-model')
        self.assertIn(b'EUR 150', seen['prompt'])
        self.assertIn(b'Europe', seen['prompt'])
        self.assertIn('read-only', seen['command'])
        self.assertNotIn('DATABASE_URL', seen['kwargs']['env'])
        self.assertNotIn('SECRET_KEY', seen['kwargs']['env'])
        self.assertIn(b'Used parts in Portugal', seen['prompt'])
        self.assertTrue(result['web_search_observed'])
        self.assertEqual(result['total_tokens'], 150)
        self.assertFalse(seen['schema']['additionalProperties'])

    def test_worker_loops_with_both_providers(self):
        self.conn.execute("UPDATE ai_connections SET models=%s, api_key='configured' WHERE provider='openwebui'", (Jsonb(['vision-model']),))
        for provider in ('codex', 'openwebui'):
            with self.subTest(provider=provider):
                self.enqueue(model=provider if provider == 'codex' else 'openwebui:vision-model', preferred_options='2')
                job = self.conn.execute("SELECT * FROM searches WHERE request_id=%s AND status='queued'", (self.order_id,)).fetchone()
                responses = [{'result': json.dumps({'summary_markdown': 'Checked live listings',
                    'listings': [{'url': f'https://example.com/{provider}/{i}', 'title': 'New option'}],
                    'research_notes': {'next_queries': ['alternative reference']}}),
                    'sources': [], 'web_search_observed': True, 'total_tokens': 100} for i in range(2)]
                with patch(f'worker.run_{provider}', side_effect=responses) as run:
                    process_job(job)
                self.assertEqual(run.call_count, 2)
                updated = self.conn.execute('SELECT * FROM searches WHERE id=%s', (job['id'],)).fetchone()
                self.assertEqual(updated['status'], 'completed')
                self.assertEqual(len(updated['listings']), 2)
                self.assertEqual(len(updated['research_meta']['rounds']), 2)
                second = run.call_args.args[0]
                self.assertEqual(second['research_round']['previous_research']['next_queries'], ['alternative reference'])
                self.assertTrue(any(item['url'].endswith(f'{provider}/0') for item in second['excluded_listings']))
                self.assertEqual(len(run.call_args.args[1]), 1)

    def test_worker_filters_blacklist_added_after_queueing(self):
        self.enqueue(preferred_options='1')
        job = self.job()
        url = 'https://example.com/blocked'
        self.conn.execute('INSERT INTO listing_blacklist(request_id,url,url_key) VALUES (%s,%s,%s)',
                          (self.order_id, url, listing_key(url)))
        result = {'result': json.dumps({'summary_markdown': '[Blocked](https://example.com/blocked?utm_source=x)',
                    'listings': [{'url': url + '?utm_source=x'}]}),
                  'sources': [url], 'web_search_observed': True}
        with patch('worker.run_codex', return_value=result) as run:
            process_job(job)
        self.assertEqual(run.call_args.args[0]['excluded_listings'][0]['url'], url)
        updated = self.job()
        self.assertEqual(updated['listings'], [])
        self.assertEqual(updated['sources'], [])
        self.assertNotIn('/blocked', updated['result'])

    def test_openwebui_manual_cancellation_stops_only_its_tasks(self):
        self.enqueue()
        replies = [httpx.Response(200, json=value) for value in (
            {'features': {'enable_web_search': True}}, {'id': 'owned-chat'},
            {'task_ids': ['owned-task']}, {'task_ids': ['owned-task']}, {'status': True})]
        with patch('search.check_openwebui', return_value=['vision-model']), patch('search.cipher') as encryption, \
                patch('search.httpx.Client') as client, patch('search.time.monotonic', side_effect=[0, 601]):
            encryption.return_value.decrypt.return_value = b'test-key'
            request = client.return_value.__enter__.return_value.request
            request.side_effect = replies
            with self.assertRaisesRegex(ValueError, 'research cancelled'):
                run_openwebui(dict(self.job(), model='vision-model'), [],
                              {'base_url': 'https://example.com', 'api_key': 'encrypted'}, lambda url: None, is_cancelled=lambda: True)
        self.assertEqual(request.call_args.args, ('POST', 'api/tasks/stop/owned-task'))

    def test_sources_reject_unsafe_urls(self):
        self.assertEqual(source_links([{'url': 'javascript:alert(1)'}, {'source': 'file:///etc/passwd'},
                                       {'url': 'https://example.com/item'}, {'url': 'https://example.com/item'}]),
                         ['https://example.com/item'])

    def test_markdown_formatting_and_security(self):
        html = str(render_markdown('## Matches\n\n**Good option**\n\n- [Seller](https://example.com)\n\nhttps://example.org\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n![image](https://example.com/tracker)'))
        for value in ('<h2>Matches</h2>', '<strong>Good option</strong>', '<ul>', 'href="https://example.com"', 'href="https://example.org"'):
            self.assertIn(value, html)
        for value in ('<script>', 'href="javascript:', '<img'):
            self.assertNotIn(value, html)

    def test_history_active_state(self):
        self.enqueue()
        page = self.client.get(f'/requests/{self.order_id}').get_data(as_text=True)
        self.assertTrue(page_data(page)['active_search'])
        self.conn.execute("UPDATE searches SET status='completed', result='**Found**' WHERE request_id=%s", (self.order_id,))
        page = self.client.get(f'/requests/{self.order_id}').get_data(as_text=True)
        self.assertFalse(page_data(page)['active_search'])
        self.assertEqual(page_data(page)['searches'][0]['result'], '**Found**')

    def test_structured_results_are_saved_and_rendered(self):
        self.enqueue()
        answer = json.dumps({'summary_markdown': '## Possible matches', 'listings': [{
            'title': '<script>unsafe</script>', 'url': 'https://example.com/part',
            'image_url': 'https://example.com/photo.jpg', 'price': '€180',
            'description': 'Rear axle', 'pickup': 'available', 'shipping': 'unknown'}]})
        with patch('worker.run_codex', return_value={'result': answer, 'sources': [], 'web_search_observed': True}):
            process_job(self.job())
        self.assertEqual(self.job()['listings'][0]['price'], '€180')
        self.assertEqual(self.job()['result'], '## Possible matches')
        page = self.client.get(f'/requests/{self.order_id}').get_data(as_text=True)
        listing = page_data(page)['found_parts'][0]
        for key, value in {'price': '€180', 'pickup': 'available', 'shipping': 'unknown', 'image_url': 'https://example.com/photo.jpg'}.items():
            self.assertEqual(listing[key], value)
        self.assertNotIn('<script>unsafe</script>', page)

    def test_structured_output_fallback_and_validation(self):
        self.assertEqual(parse_research('Ordinary **Markdown**'), ('Ordinary **Markdown**', []))
        self.assertEqual(parse_research('{broken'), ('{broken', []))
        for url in ('javascript:alert(1)', 'https://127.0.0.1/x', 'https://server.local/x', 'https://user:pass@example.com/x'):
            self.assertEqual(public_url(url), '')
        self.assertEqual(public_url('http://example.com/image', image=True), '')
        summary, items = parse_research(json.dumps({'summary_markdown': 'No price', 'listings': [
            {'url': 'javascript:alert(1)'}, {'url': 'https://example.com', 'price': None, 'shipping': True}]}))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['price'], '')
        self.assertEqual(items[0]['shipping'], 'unknown')
        self.assertEqual(items[0]['visual_status'], 'not_checked')

    def test_visual_comparison_fields_and_instructions(self):
        _, items = parse_research(json.dumps({'summary_markdown': 'Check fitment', 'listings': [{
            'url': 'https://example.com/part', 'visual_status': 'compared',
            'visual_comparison': 'Mounting brackets look similar; rear face not visible.',
            'variant_checks': 'Drum brakes shown; ABS variant unknown.'}]}))
        self.assertEqual(items[0]['visual_status'], 'compared')
        self.assertIn('rear face', items[0]['visual_comparison'])
        self.assertIn('ABS', items[0]['variant_checks'])
        self.assertIn('A search snippet, title, image URL or image caption is NOT visual inspection', SYSTEM_PROMPT)
        self.assertIn('Exclude candidates with visible or documented fitment contradictions', SYSTEM_PROMPT)

    def test_preferred_option_count(self):
        for value in ('0', '21', '-1', 'six', '2.5', ''):
            self.assertEqual(self.enqueue(preferred_options=value).status_code, 400)
        self.assertEqual(self.enqueue(preferred_options='8').status_code, 303)
        self.assertEqual(self.job()['preferred_options'], 8)
        self.assertEqual(json.loads(prompt_for(self.job()))['preferred_options'], 8)
        page = self.client.get(f'/requests/{self.order_id}').get_data(as_text=True)
        self.assertEqual(page_data(page)['searches'][0]['preferred_options'], 8)
        self.assertIn('soft target, never a quota', SYSTEM_PROMPT)

    def test_priority_websites_management_and_snapshot(self):
        self.assertEqual(self.client.get('/websites').status_code, 200)
        self.assertEqual(self.client.post('/websites', data={'csrf': 'bad'}).status_code, 400)
        self.assertEqual(self.client.post('/websites', data={'csrf': self.csrf, 'urls': 'https://server.local'}).status_code, 400)
        response = self.client.post('/websites', data={'csrf': self.csrf,
            'urls': 'https://example.com/\nhttps://example.org\nhttps://example.com'})
        self.assertEqual(response.status_code, 303)
        self.enqueue()
        expected = ['https://example.com', 'https://example.org']
        self.assertEqual(self.job()['priority_websites'], expected)
        self.assertEqual(json.loads(prompt_for(self.job()))['priority_websites'], expected)
        self.client.post('/websites', data={'csrf': self.csrf, 'urls': ''})
        self.assertEqual(self.job()['priority_websites'], expected)
        self.assertEqual(page_data(self.client.get(f'/requests/{self.order_id}'))['searches'][0]['priority_websites'], expected)

    def test_availability_filters_and_requires_evidence(self):
        items = [{'url': 'https://example.com/part', 'availability': status}
                 for status in ('sold', 'reserved', 'unavailable', 'listed_available', 'unknown')]
        items.append({'url': 'https://example.com/stock', 'availability': 'listed_available',
                      'availability_evidence': 'Listing states: In stock.'})
        _, listings = parse_research(json.dumps({'summary_markdown': 'Stock checked', 'listings': items}))
        self.assertEqual(len(listings), 3)
        self.assertEqual([item['availability'] for item in listings], ['unknown', 'unknown', 'listed_available'])
        self.assertIn('Check CURRENT availability', SYSTEM_PROMPT)

    def test_car_profile_snapshot_and_prompt(self):
        response = self.client.post('/cars/new', data={'csrf': self.csrf, 'name': 'R19 test',
            'make': 'Renault', 'model': '19', 'year': '1991', 'abs': 'No', 'rear_brakes': 'Drums'})
        car_id = response.location.rsplit('/', 1)[-1]
        self.conn.execute('UPDATE requests SET car_id=%s WHERE id=%s', (car_id, self.order_id))
        self.enqueue()
        job = self.job()
        self.assertEqual(job['car_profile']['rear_brakes'], 'Drums')
        self.assertEqual(json.loads(prompt_for(job))['car_profile']['abs'], 'No')
        self.conn.execute("UPDATE cars SET specs=%s WHERE id=%s", (Jsonb({'rear_brakes': 'Discs'}), car_id))
        self.assertEqual(self.job()['car_profile']['rear_brakes'], 'Drums')
        self.assertEqual(page_data(self.client.get(f'/requests/{self.order_id}'))['searches'][0]['car_profile']['rear_brakes'], 'Drums')

    def test_parts_found_previously_found_listing_is_not_returned_again(self):
        for price in ('€100', '€90'):
            self.enqueue()
            job = self.conn.execute("SELECT * FROM searches WHERE request_id=%s AND status='queued'", (self.order_id,)).fetchone()
            # now() is transaction-scoped in this rollback test; set deterministic ordering.
            self.conn.execute('UPDATE searches SET created_at=clock_timestamp() WHERE id=%s', (job['id'],))
            answer = json.dumps({'summary_markdown': 'Found', 'listings': [{
                'url': 'https://example.com/part', 'title': 'Rear axle', 'price': price}]})
            with patch('worker.run_codex', return_value={'result': answer, 'sources': [], 'web_search_observed': True}):
                process_job(job)
        page = self.client.get(f'/requests/{self.order_id}').get_data(as_text=True)
        cards = page_data(page)['found_parts']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['price'], '€100')
        latest = self.conn.execute('SELECT listings, result FROM searches WHERE id=%s', (job['id'],)).fetchone()
        self.assertEqual(latest['listings'], [])
        self.assertIn('No new eligible listings', latest['result'])

    def test_blacklist_remove_restore_and_future_search_snapshot(self):
        self.enqueue()
        job = self.job()
        url = 'https://example.com/part?id=42&utm_source=search#photo'
        self.conn.execute("UPDATE searches SET status='completed', listings=%s WHERE id=%s",
                          (Jsonb([{'url': url, 'title': 'Rear axle'}]), job['id']))
        endpoint = f'/requests/{self.order_id}/blacklist'
        self.assertEqual(self.client.post(endpoint, data={'url': url}).status_code, 400)
        self.assertEqual(self.client.post(endpoint, data={'csrf': self.csrf, 'url': 'https://example.com/other'}).status_code, 404)
        data = {'csrf': self.csrf, 'url': url, 'reason': 'Wrong mounting points'}
        self.assertEqual(self.client.post(endpoint, data=data).status_code, 303)
        self.assertEqual(self.client.post(endpoint, data=data).status_code, 303)
        entries = self.conn.execute('SELECT * FROM listing_blacklist WHERE request_id=%s', (self.order_id,)).fetchall()
        self.assertEqual(len(entries), 1)
        page = self.client.get(f'/requests/{self.order_id}').get_data(as_text=True)
        self.assertEqual(page_data(page)['found_parts'], [])
        self.assertIn('Wrong mounting points', page)
        self.assertEqual(len(page_data(page)['blacklist']), 1)
        self.enqueue()
        next_job = self.conn.execute("SELECT * FROM searches WHERE request_id=%s AND status='queued'", (self.order_id,)).fetchone()
        self.assertEqual(json.loads(prompt_for(next_job))['excluded_listings'], [{'url': url, 'reason': data['reason']}])
        # Even an AI that ignores the exclusion cannot bring the card back.
        self.conn.execute("UPDATE searches SET status='completed', listings=%s WHERE id=%s",
                          (Jsonb([{'url': 'https://example.com/part?utm_source=other&id=42', 'title': 'Rear axle'}]), next_job['id']))
        self.assertEqual(page_data(self.client.get(f'/requests/{self.order_id}'))['found_parts'], [])
        restore = f"{endpoint}/{entries[0]['id']}/restore"
        self.assertEqual(self.client.post(restore).status_code, 400)
        self.assertEqual(self.client.post(restore, data={'csrf': self.csrf}).status_code, 303)
        self.assertEqual(len(page_data(self.client.get(f'/requests/{self.order_id}'))['found_parts']), 1)
        self.assertEqual(next_job['excluded_listings'][0]['url'], url)

    def test_blacklist_scope_and_scheduled_snapshot(self):
        import uuid
        from scheduling import enqueue_search
        self.enqueue(action='schedule', weekdays=['0'], time_0='16:30')
        schedule = self.conn.execute('SELECT * FROM schedules WHERE request_id=%s', (self.order_id,)).fetchone()
        url = 'https://example.com/part'
        entry = self.conn.execute('''INSERT INTO listing_blacklist(request_id, url, url_key, reason)
            VALUES (%s, %s, %s, %s) RETURNING id''', (self.order_id, url, listing_key(url), 'Wrong version')).fetchone()
        other_id = uuid.uuid4()
        self.conn.execute('INSERT INTO requests(id, description, vehicle) VALUES (%s,%s,%s)',
                          (other_id, 'Another rear axle request', 'Renault'))
        other = self.conn.execute('SELECT * FROM requests WHERE id=%s', (other_id,)).fetchone()
        other_job = enqueue_search(self.conn, other, schedule['settings'])
        self.assertEqual(self.conn.execute('SELECT excluded_listings FROM searches WHERE id=%s', (other_job,)).fetchone()['excluded_listings'], [])
        self.assertEqual(self.client.post(f"/requests/{other_id}/blacklist/{entry['id']}/restore", data={'csrf': self.csrf}).status_code, 404)
        now = datetime.now(timezone.utc)
        self.conn.execute('UPDATE schedules SET next_run=%s WHERE id=%s', (now - timedelta(seconds=1), schedule['id']))
        self.assertEqual(dispatch_due(self.conn, now), 1)
        self.assertEqual(self.job()['excluded_listings'], [{'url': url, 'reason': 'Wrong version'}])

    def test_listing_key_keeps_product_identifiers(self):
        self.assertEqual(listing_key('https://EXAMPLE.com/item?id=1&utm_medium=x#photo'), listing_key('https://example.com/item?id=1'))
        self.assertNotEqual(listing_key('https://example.com/item?id=1'), listing_key('https://example.com/item?id=2'))

    def test_schedule_excludes_parts_found_at_dispatch_time(self):
        self.enqueue(action='schedule', weekdays=['0'], time_0='16:30')
        self.enqueue()
        previous = self.job()
        found_url = 'https://example.com/already-found'
        self.conn.execute("UPDATE searches SET status='completed', listings=%s WHERE id=%s",
                          (Jsonb([{'url': found_url}]), previous['id']))
        now = datetime.now(timezone.utc)
        self.conn.execute('UPDATE schedules SET next_run=%s WHERE request_id=%s', (now - timedelta(seconds=1), self.order_id))
        self.assertEqual(dispatch_due(self.conn, now), 1)
        scheduled = self.conn.execute("SELECT excluded_listings FROM searches WHERE request_id=%s AND status='queued'", (self.order_id,)).fetchone()
        self.assertEqual(scheduled['excluded_listings'], [{'url': found_url, 'reason': 'Already in Parts Found.'}])

    def test_weekly_schedule_settings_and_dispatch(self):
        response = self.enqueue(action='schedule', weekdays=['0', '3'], time_0='16:30', time_3='20:50',
                                preferred_options='8', preferred_price='€150', shipping_areas='Europe')
        self.assertEqual(response.status_code, 303)
        self.assertIsNone(self.job())
        rows = self.conn.execute('SELECT * FROM schedules WHERE request_id=%s ORDER BY weekday', (self.order_id,)).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['local_time'], time(16, 30))
        self.assertEqual(rows[1]['local_time'], time(20, 50))
        self.assertEqual(rows[0]['settings']['preferred_options'], 8)
        now = datetime.now(timezone.utc)
        self.conn.execute('UPDATE schedules SET next_run=%s WHERE id=%s', (now - timedelta(seconds=1), rows[0]['id']))
        self.conn.execute('UPDATE requests SET vehicle=%s WHERE id=%s', ('Updated vehicle', self.order_id))
        self.assertEqual(dispatch_due(self.conn, now), 1)
        job = self.job()
        self.assertEqual(job['vehicle'], 'Updated vehicle')
        self.assertEqual(job['preferred_options'], 8)
        self.assertEqual(job['shipping_areas'], 'Europe')
        self.assertEqual(job['schedule_id'], rows[0]['id'])
        self.assertEqual(dispatch_due(self.conn, now), 0)
        self.assertEqual(page_data(self.client.get(f'/requests/{self.order_id}'))['searches'][0]['schedule_id'], str(rows[0]['id']))

    def test_schedule_validation_update_disable_delete(self):
        for fields in ({}, {'weekdays': '7'}, {'weekdays': '0', 'time_0': '25:00'}):
            self.assertEqual(self.enqueue(action='schedule', **fields).status_code, 400)
        self.enqueue(action='schedule', weekdays='0', time_0='16:30')
        self.enqueue(action='schedule', weekdays='0', time_0='16:30', preferred_options='10')
        rows = self.conn.execute('SELECT * FROM schedules WHERE request_id=%s', (self.order_id,)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['settings']['preferred_options'], 10)
        url = f'/requests/{self.order_id}/schedules/{rows[0]["id"]}'
        self.assertEqual(self.client.post(url, data={'csrf': 'bad', 'action': 'delete'}).status_code, 400)
        self.assertEqual(self.client.post(url, data={'csrf': self.csrf, 'action': 'disable'}).status_code, 303)
        self.assertFalse(self.conn.execute('SELECT enabled FROM schedules WHERE id=%s', (rows[0]['id'],)).fetchone()['enabled'])
        self.client.post(url, data={'csrf': self.csrf, 'action': 'enable'})
        self.assertTrue(self.conn.execute('SELECT enabled FROM schedules WHERE id=%s', (rows[0]['id'],)).fetchone()['enabled'])
        self.client.post(url, data={'csrf': self.csrf, 'action': 'delete'})
        self.assertIsNone(self.conn.execute('SELECT id FROM schedules WHERE id=%s', (rows[0]['id'],)).fetchone())

    def test_due_schedule_waits_for_active_search(self):
        self.enqueue()
        self.assertEqual(self.enqueue(action='schedule', weekdays='0', time_0='16:30').status_code, 303)
        now = datetime.now(timezone.utc)
        self.conn.execute('UPDATE schedules SET next_run=%s WHERE request_id=%s', (now - timedelta(days=20), self.order_id))
        self.assertEqual(dispatch_due(self.conn, now), 0)
        self.conn.execute("UPDATE searches SET status='completed' WHERE request_id=%s", (self.order_id,))
        self.assertEqual(dispatch_due(self.conn, now), 1)
        self.assertEqual(dispatch_due(self.conn, now), 0)

    def test_lisbon_weekly_time_and_dst(self):
        before = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
        self.assertEqual(next_occurrence(0, time(16, 30), before), datetime(2026, 9, 21, 15, 30, tzinfo=timezone.utc))
        spring = next_occurrence(6, time(1, 30), datetime(2026, 3, 28, tzinfo=timezone.utc))
        self.assertEqual(spring, datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc))
        autumn = next_occurrence(6, time(1, 30), datetime(2026, 10, 24, tzinfo=timezone.utc))
        self.assertEqual(autumn, datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc))
        self.assertEqual(next_occurrence(6, time(1, 30), autumn).date().isoformat(), '2026-11-01')

    def test_openwebui_requires_enabled_search(self):
        self.enqueue()
        job = dict(self.job(), model='vision-model')
        with patch('search.check_openwebui', return_value=['vision-model']), patch('search.cipher') as encryption, patch('search.httpx.Client') as client:
            encryption.return_value.decrypt.return_value = b'test-key'
            client.return_value.__enter__.return_value.request.return_value = httpx.Response(200, json={'features': {'enable_web_search': False}})
            with self.assertRaisesRegex(ValueError, 'Enable web search'):
                run_openwebui(job, [], {'base_url': 'https://example.com', 'api_key': 'encrypted'}, lambda url: None)
            self.assertEqual(client.return_value.__enter__.return_value.request.call_count, 1)

    def test_result_without_web_evidence_is_labelled(self):
        self.enqueue()
        with patch('worker.run_codex', return_value={'result': 'Possible part identification.', 'sources': [], 'web_search_observed': False}):
            process_job(self.job())
        response = self.client.get(f'/requests/{self.order_id}')
        self.assertFalse(page_data(response)['searches'][0]['web_search_observed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
