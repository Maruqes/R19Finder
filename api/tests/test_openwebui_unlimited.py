import unittest
from unittest.mock import patch

import httpx
from search import run_openwebui


class OpenWebUIUnlimitedTests(unittest.TestCase):
    def test_openwebui_native_research_includes_images_and_web_search(self):
        job = dict(id='test', vehicle='Renault 19', model='vision-model', instructions='Find part', round_timeout_seconds=-1)
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

        with patch('search.check_openwebui', return_value=['vision-model']), patch('search.cipher') as encryption, patch('search.httpx.Client') as client, patch('search.time.sleep') as sleep, patch('search.time.monotonic', side_effect=AssertionError('Unexpected time limit')), patch('search.prompt_for', return_value='Find part'):
            encryption.return_value.decrypt.return_value = b'test-key'
            client.return_value.__enter__.return_value.request.side_effect = respond
            remote = []
            result = run_openwebui(job, [{'data': b'jpeg-test'}],
                                  {'base_url': 'https://openwebui.test', 'api_key': 'encrypted'}, remote.append)
        self.assertIsNone(client.call_args.kwargs['timeout'])
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

    def test_openwebui_manual_cancellation_stops_only_its_tasks(self):
        replies = [httpx.Response(200, json=value) for value in (
            {'features': {'enable_web_search': True}}, {'id': 'owned-chat'},
            {'task_ids': ['owned-task']}, {'task_ids': ['owned-task']}, {'status': True})]
        with patch('search.check_openwebui', return_value=['vision-model']), patch('search.cipher') as encryption, \
                patch('search.httpx.Client') as client, patch('search.prompt_for', return_value='Find part'):
            encryption.return_value.decrypt.return_value = b'test-key'
            request = client.return_value.__enter__.return_value.request
            request.side_effect = replies
            with self.assertRaisesRegex(ValueError, 'research cancelled'):
                run_openwebui(dict(id='test', vehicle='Renault 19', model='vision-model'), [],
                              {'base_url': 'https://example.com', 'api_key': 'encrypted'}, lambda url: None, is_cancelled=lambda: True)
        self.assertEqual(request.call_args.args, ('POST', 'api/tasks/stop/owned-task'))

