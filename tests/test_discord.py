import asyncio
from datetime import datetime, timedelta, timezone
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from psycopg.types.json import Jsonb

from app import app, connect
from ai import cipher
from discord_integration import (
    DiscordError, api_request, deliver_next, finish_rejection, listing_payload,
    prepare_rejection, command_summary,
)
from listings import listing_key
from scheduling import dispatch_due, enqueue_search
from worker import process_job

OWNER = '123456789012345678'
CHANNEL = '234567890123456789'
MESSAGE = '345678901234567890'
TOKEN = 'test-discord-token-1234567890'


class DiscordTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        self.transaction = self.conn.transaction(force_rollback=True)
        self.transaction.__enter__()
        class SharedConnection:
            def __enter__(_self):
                return self.conn
            def __exit__(_self, *args):
                return False
        self.connect = lambda: SharedConnection()
        self.patches = [patch('app.connect', self.connect), patch('worker.connect', self.connect),
                        patch('search.check_codex', return_value='Authenticated'),
                        patch('discord_integration.httpx.request', side_effect=AssertionError('Unexpected external request'))]
        for item in self.patches:
            item.start()
        self.conn.execute('DELETE FROM discord_notifications')
        self.conn.execute('DELETE FROM discord_confirmations')
        self.conn.execute("UPDATE discord_settings SET bot_token='', enabled=FALSE, channel_id='', owner_id='', status='unconfigured', heartbeat_at=NULL")
        self.client = app.test_client()
        self.client.get('/discord')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']
        response = self.client.post('/requests', data={'csrf': self.csrf, 'vehicle': 'Renault 19',
                                                      'description': 'Left rear light for Renault 19'})
        self.order_id = uuid.UUID(response.location.rsplit('/', 1)[-1])
        self.part = {'url': 'https://example.com/part?id=1', 'title': 'Farolim @everyone', 'price': '45 EUR',
                     'location': 'Porto', 'description': 'Farolim esquerdo', 'image_url': ''}

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.transaction.__exit__(None, None, None)
        self.conn.close()

    def save(self, **overrides):
        return self.client.post('/discord', data=dict({'csrf': self.csrf, 'bot_token': TOKEN,
            'channel_id': CHANNEL, 'owner_id': OWNER, 'enabled': '1', 'app_url': ''}, **overrides))

    def schedule(self, enabled=True):
        response = self.client.post(f'/requests/{self.order_id}/search', data={'csrf': self.csrf,
            'model': 'codex', 'action': 'schedule', 'weekdays': '0', 'time_0': '16:30',
            'discord_notify': '1' if enabled else '0'})
        self.assertEqual(response.status_code, 303)
        return self.conn.execute('SELECT * FROM schedules WHERE request_id=%s', (self.order_id,)).fetchone()

    def completed_job(self, parts=None):
        self.save()
        schedule = self.schedule()
        order = self.conn.execute('SELECT * FROM requests WHERE id=%s', (self.order_id,)).fetchone()
        search_id = enqueue_search(self.conn, order, schedule['settings'], schedule['id'], True)
        self.conn.execute("UPDATE searches SET status='completed', listings=%s WHERE id=%s", (Jsonb(parts or [self.part]), search_id))
        self.conn.execute('INSERT INTO discord_notifications (search_id) VALUES (%s)', (search_id,))
        return search_id, schedule['id']

    def notification(self, search_id):
        return self.conn.execute('SELECT * FROM discord_notifications WHERE search_id=%s', (search_id,)).fetchone()

    def delivered_job(self):
        search_id, schedule_id = self.completed_job()
        with patch('discord_integration.httpx.request', return_value=httpx.Response(200, json={'id': MESSAGE})):
            self.assertTrue(deliver_next(self.connect))
        return search_id, schedule_id

    def test_settings_encryption_validation_and_csrf(self):
        self.assertEqual(self.save(csrf='bad').status_code, 400)
        for values in ({'owner_id': 'not-an-id'}, {'channel_id': '../secret'}, {'bot_token': 'bad token'},
                       {'app_url': 'https://user:password@example.com'}, {'app_url': 'javascript:alert(1)'}):
            self.assertEqual(self.save(**values).status_code, 400)
        self.assertEqual(self.save(bot_token='').status_code, 400)
        self.assertEqual(self.save().status_code, 303)
        config = self.conn.execute('SELECT * FROM discord_settings WHERE id=1').fetchone()
        self.assertEqual(cipher().decrypt(config['bot_token'].encode()).decode(), TOKEN)
        self.assertNotEqual(config['bot_token'], TOKEN)
        html = self.client.get('/discord').get_data(as_text=True)
        self.assertNotIn(TOKEN, html)
        self.assertNotIn(config['bot_token'], html)
        self.assertEqual(self.save(bot_token='').status_code, 303)
        self.assertEqual(self.conn.execute('SELECT bot_token FROM discord_settings WHERE id=1').fetchone()['bot_token'], config['bot_token'])
        html = self.save(bot_token='bad token', owner_id='bad').get_data(as_text=True)
        self.assertNotIn('bad token', html)

    def test_check_is_read_only_and_remote_errors_are_redacted(self):
        self.save()
        with patch('discord_integration.httpx.request', side_effect=[httpx.Response(200, json={'bot': True}),
                   httpx.Response(200, json={'type': 0, 'guild_id': '123', 'name': 'parts'})]) as api:
            self.assertEqual(self.client.post('/discord/test', data={'csrf': self.csrf}).status_code, 200)
            self.assertTrue(all(call.args[0] == 'GET' for call in api.call_args_list))
            self.assertTrue(all(not call.kwargs['follow_redirects'] for call in api.call_args_list))
        for status in (401, 403, 404, 302, 500):
            with patch('discord_integration.httpx.request', return_value=httpx.Response(status, text='private remote details')):
                response = self.client.post('/discord/test', data={'csrf': self.csrf})
                self.assertNotIn(b'private remote details', response.data)
                self.assertNotIn(TOKEN.encode(), response.data)
        self.assertEqual(self.client.post('/discord/test', data={'csrf': 'bad'}).status_code, 400)

    def test_schedule_toggle_and_dispatch_snapshot(self):
        schedule = self.schedule(False)
        self.assertFalse(schedule['discord_notify'])
        path = f'/requests/{self.order_id}/schedules/{schedule["id"]}'
        self.assertEqual(self.client.post(path, data={'csrf': 'bad', 'action': 'discord', 'discord_notify': '1'}).status_code, 400)
        self.assertEqual(self.client.post(path, data={'csrf': self.csrf, 'action': 'discord', 'discord_notify': '1'}).status_code, 303)
        updated = self.conn.execute('SELECT * FROM schedules WHERE id=%s', (schedule['id'],)).fetchone()
        self.assertTrue(updated['discord_notify'])
        self.assertEqual(updated['next_run'], schedule['next_run'])
        self.assertEqual(updated['settings'], schedule['settings'])
        self.conn.execute('UPDATE schedules SET next_run=now() WHERE id=%s', (schedule['id'],))
        dispatch_due(self.conn)
        queued = self.conn.execute('SELECT * FROM searches WHERE request_id=%s', (self.order_id,)).fetchone()
        self.assertTrue(queued['discord_notify'])
        self.client.post(path, data={'csrf': self.csrf, 'action': 'discord'})
        self.assertFalse(self.conn.execute('SELECT discord_notify FROM schedules WHERE id=%s', (schedule['id'],)).fetchone()['discord_notify'])
        html = self.client.get(f'/requests/{self.order_id}').data
        self.assertIn(b'role="switch"', html)
        self.assertIn(b'/discord', html)

    def test_updating_slot_and_manual_search_do_not_leak_notifications(self):
        first = self.schedule(True)
        second = self.schedule(False)
        self.assertEqual(first['id'], second['id'])
        self.assertFalse(second['discord_notify'])
        response = self.client.post(f'/requests/{self.order_id}/search', data={'csrf': self.csrf,
            'model': 'codex', 'discord_notify': '1'})
        self.assertEqual(response.status_code, 303)
        self.assertFalse(self.conn.execute('SELECT discord_notify FROM searches WHERE request_id=%s', (self.order_id,)).fetchone()['discord_notify'])
        other = self.client.post('/requests', data={'csrf': self.csrf, 'description': 'Another unrelated request'}).location
        self.assertEqual(self.client.post(other + '/schedules/' + str(first['id']), data={'csrf': self.csrf, 'action': 'discord', 'discord_notify': '1'}).status_code, 404)

    def test_worker_queues_only_new_scheduled_results(self):
        schedule = self.schedule(True)
        order = self.conn.execute('SELECT * FROM requests WHERE id=%s', (self.order_id,)).fetchone()
        for enabled, scheduled, parts in ((True, True, [self.part]), (False, True, [self.part]),
                                           (True, False, [self.part]), (True, True, [])):
            search_id = enqueue_search(self.conn, order, schedule['settings'], schedule['id'] if scheduled else None, enabled)
            job = self.conn.execute('SELECT * FROM searches WHERE id=%s', (search_id,)).fetchone()
            result = {'listings': parts, 'result': 'Results', 'sources': [], 'web_search_observed': True, 'research_meta': {}}
            # Isolate cases from previously saved listings.
            self.conn.execute("UPDATE searches SET listings='[]' WHERE request_id=%s", (self.order_id,))
            with patch('worker.run_research', return_value=result):
                process_job(job)
            self.assertEqual(self.notification(search_id) is not None, enabled and scheduled and bool(parts))

    def test_delivery_payload_and_no_duplicate_send(self):
        search_id, _ = self.completed_job()
        with patch('discord_integration.httpx.request', return_value=httpx.Response(200, json={'id': MESSAGE})) as send:
            deliver_next(self.connect)
            deliver_next(self.connect)
        self.assertEqual(send.call_count, 1)
        payload = send.call_args.kwargs['json']
        self.assertEqual(payload['allowed_mentions'], {'parse': [], 'users': [OWNER]})
        self.assertTrue(payload['enforce_nonce'])
        self.assertLessEqual(len(payload['nonce']), 25)
        self.assertEqual(payload['components'][0]['components'][1]['label'], 'Reject')
        self.assertEqual(self.notification(search_id)['status'], 'sent')
        self.assertNotIn('@everyone', payload['embeds'][0]['title'])

    def test_partial_delivery_resumes_without_resending(self):
        search_id, _ = self.completed_job([self.part, dict(self.part, url='https://example.com/part?id=2')])
        with patch('discord_integration.httpx.request', return_value=httpx.Response(200, json={'id': MESSAGE})):
            deliver_next(self.connect)
        self.assertEqual(self.notification(search_id)['status'], 'pending')
        self.conn.execute('UPDATE discord_notifications SET next_attempt=now() WHERE search_id=%s', (search_id,))
        with patch('discord_integration.httpx.request', return_value=httpx.Response(200, json={'id': '456789012345678901'})) as send:
            deliver_next(self.connect)
        self.assertIn('id=2', send.call_args.kwargs['json']['embeds'][0]['url'])
        self.assertEqual(len(self.notification(search_id)['messages']), 2)
        self.assertEqual(self.notification(search_id)['status'], 'sent')

    def test_skip_disabled_deleted_and_blacklisted(self):
        for change in ('disable', 'delete', 'blacklist'):
            search_id, schedule_id = self.completed_job()
            if change == 'disable':
                self.conn.execute('UPDATE schedules SET discord_notify=FALSE WHERE id=%s', (schedule_id,))
            elif change == 'delete':
                self.conn.execute('DELETE FROM schedules WHERE id=%s', (schedule_id,))
            else:
                self.client.post(f'/requests/{self.order_id}/blacklist', data={'csrf': self.csrf, 'url': self.part['url']})
            deliver_next(self.connect)
            self.assertEqual(self.notification(search_id)['status'], 'skipped')

    def test_retry_transient_and_permanent_failure_preserves_results(self):
        search_id, _ = self.completed_job()
        with patch('discord_integration.httpx.request', return_value=httpx.Response(429, json={'retry_after': 120})):
            deliver_next(self.connect)
        row = self.notification(search_id)
        self.assertEqual(row['status'], 'pending')
        self.assertGreater(row['next_attempt'], datetime.now(timezone.utc) + timedelta(seconds=110))
        self.conn.execute('UPDATE discord_notifications SET next_attempt=now() WHERE search_id=%s', (search_id,))
        with patch('discord_integration.httpx.request', return_value=httpx.Response(403, text=TOKEN)):
            deliver_next(self.connect)
        self.assertEqual(self.notification(search_id)['status'], 'failed')
        self.assertNotIn(TOKEN, self.notification(search_id)['last_error'])
        self.assertEqual(self.conn.execute('SELECT status FROM searches WHERE id=%s', (search_id,)).fetchone()['status'], 'completed')
        self.assertEqual(self.client.post(f'/discord/notifications/{search_id}/retry', data={'csrf': 'bad'}).status_code, 400)
        self.assertEqual(self.client.post(f'/discord/notifications/{search_id}/retry', data={'csrf': self.csrf}).status_code, 303)
        self.assertEqual(self.notification(search_id)['status'], 'pending')

    def test_configuration_pause_prevents_send(self):
        search_id, _ = self.completed_job()
        self.conn.execute('UPDATE discord_settings SET enabled=FALSE WHERE id=1')
        self.assertFalse(deliver_next(self.connect))
        self.assertEqual(self.notification(search_id)['status'], 'pending')

    def test_rejection_requires_confirmation_and_cancel_preserves_listing(self):
        search_id, _ = self.delivered_job()
        confirmation, _ = prepare_rejection(self.connect, OWNER, CHANNEL, MESSAGE, search_id, 0)
        self.assertFalse(self.conn.execute('SELECT 1 FROM listing_blacklist WHERE request_id=%s', (self.order_id,)).fetchone())
        finish_rejection(self.connect, OWNER, CHANNEL, uuid.UUID(confirmation), False)
        self.assertFalse(self.conn.execute('SELECT 1 FROM listing_blacklist WHERE request_id=%s', (self.order_id,)).fetchone())
        with self.assertRaises(ValueError):
            finish_rejection(self.connect, OWNER, CHANNEL, uuid.UUID(confirmation), True)

    def test_confirm_blacklists_only_this_request_and_can_restore(self):
        search_id, _ = self.delivered_job()
        confirmation, _ = prepare_rejection(self.connect, OWNER, CHANNEL, MESSAGE, search_id, 0)
        finish_rejection(self.connect, OWNER, CHANNEL, uuid.UUID(confirmation), True)
        entry = self.conn.execute('SELECT * FROM listing_blacklist WHERE request_id=%s', (self.order_id,)).fetchone()
        self.assertEqual(entry['url_key'], listing_key(self.part['url']))
        self.assertEqual(entry['reason'], 'Rejected on Discord.')
        self.assertNotIn(b'class="part-card"', self.client.get(f'/requests/{self.order_id}').data)
        schedule = self.conn.execute('SELECT * FROM schedules WHERE request_id=%s', (self.order_id,)).fetchone()
        order = self.conn.execute('SELECT * FROM requests WHERE id=%s', (self.order_id,)).fetchone()
        next_id = enqueue_search(self.conn, order, schedule['settings'])
        exclusions = self.conn.execute('SELECT excluded_listings FROM searches WHERE id=%s', (next_id,)).fetchone()['excluded_listings']
        self.assertEqual(exclusions[0]['reason'], 'Rejected on Discord.')
        self.client.post(f'/requests/{self.order_id}/blacklist/{entry["id"]}/restore', data={'csrf': self.csrf})
        self.assertIn(b'class="part-card"', self.client.get(f'/requests/{self.order_id}').data)

    def test_owner_channel_message_expiry_and_replay_validation(self):
        search_id, _ = self.delivered_job()
        for user, channel, message, index in [('999999999999999999', CHANNEL, MESSAGE, 0),
                                             (OWNER, '999999999999999999', MESSAGE, 0),
                                             (OWNER, CHANNEL, '999999999999999999', 0),
                                             (OWNER, CHANNEL, MESSAGE, -1)]:
            with self.assertRaises((PermissionError, ValueError)):
                prepare_rejection(self.connect, user, channel, message, search_id, index)
        confirmation, _ = prepare_rejection(self.connect, OWNER, CHANNEL, MESSAGE, search_id, 0)
        with self.assertRaises(PermissionError):
            finish_rejection(self.connect, '999999999999999999', CHANNEL, uuid.UUID(confirmation), True)
        self.conn.execute("UPDATE discord_confirmations SET expires_at=now() - interval '1 minute' WHERE id=%s", (confirmation,))
        with self.assertRaises(ValueError):
            finish_rejection(self.connect, OWNER, CHANNEL, uuid.UUID(confirmation), True)
        self.assertFalse(self.conn.execute('SELECT 1 FROM listing_blacklist WHERE request_id=%s', (self.order_id,)).fetchone())

    def test_commands_are_scoped_and_read_only(self):
        self.save()
        self.schedule()
        self.assertIn('Renault 19', command_summary(self.connect, OWNER, CHANNEL, 'requests'))
        self.assertIn('Discord ON', command_summary(self.connect, OWNER, CHANNEL, 'schedules'))
        self.assertFalse(self.conn.execute('SELECT 1 FROM searches WHERE request_id=%s', (self.order_id,)).fetchone())
        with self.assertRaises(PermissionError):
            command_summary(self.connect, '999999999999999999', CHANNEL, 'requests')


class DiscordInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_button_prompts_before_any_blacklist_action(self):
        import discord
        from discord_worker import FinderBot
        bot = FinderBot({'version': 1})
        interaction = MagicMock()
        interaction.type = discord.InteractionType.component
        interaction.data = {'custom_id': f'r19:reject:{uuid.uuid4()}:0'}
        interaction.user.id, interaction.channel_id, interaction.message.id = int(OWNER), int(CHANNEL), int(MESSAGE)
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        with patch('discord_worker.prepare_rejection', return_value=(str(uuid.uuid4()), 'Farolim')), \
             patch('discord_worker.finish_rejection') as finish:
            await bot.on_interaction(interaction)
        finish.assert_not_called()
        sent = interaction.edit_original_response.call_args.kwargs
        self.assertIn('Reject', sent['content'])
        self.assertEqual([item.label for item in sent['view'].children], ['Confirm rejection', 'Cancel'])
        self.assertTrue(interaction.response.defer.call_args.kwargs['ephemeral'])
        sent['view'].stop()
        await bot.close()

    async def test_confirm_updates_message_after_database_success(self):
        import discord
        from discord_worker import FinderBot
        bot = FinderBot({'version': 1})
        interaction = MagicMock()
        interaction.type = discord.InteractionType.component
        interaction.data = {'custom_id': f'r19:confirm:{uuid.uuid4()}'}
        interaction.user.id, interaction.channel_id = int(OWNER), int(CHANNEL)
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        with patch('discord_worker.finish_rejection', return_value=({'channel_id': CHANNEL}, MESSAGE)) as finish, \
             patch('discord_worker.api_request') as edit:
            await bot.on_interaction(interaction)
        self.assertTrue(finish.call_args.args[-1])
        self.assertEqual(edit.call_args.args[1], 'PATCH')
        self.assertIsNone(interaction.edit_original_response.call_args.kwargs['view'])
        await bot.close()


if __name__ == '__main__':
    unittest.main()
