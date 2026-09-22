import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import httpx

from ai import check_codex, check_openwebui, cipher, validate_url
from app import app, connect


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        self.transaction = self.conn.transaction(force_rollback=True)
        self.transaction.__enter__()

        class SharedConnection:
            def __enter__(_self):
                return self.conn

            def __exit__(_self, *args):
                return False

        self.mock = patch('app.connect', return_value=SharedConnection())
        self.mock.start()
        self.client = app.test_client()
        self.client.get('/ai')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']
        self.conn.execute("UPDATE ai_connections SET api_key='', base_url='', checked_at=NULL")

    def tearDown(self):
        self.mock.stop()
        self.transaction.__exit__(None, None, None)
        self.conn.close()

    def save(self, **changes):
        data = {'csrf': self.csrf, 'base_url': 'http://openwebui:8080', 'api_key': 'test-private-key'}
        data.update(changes)
        return self.client.post('/ai/openwebui', data=data)

    def test_save_encrypt_keep_and_replace(self):
        self.assertEqual(self.save().status_code, 303)
        row = self.conn.execute("SELECT * FROM ai_connections WHERE provider='openwebui'").fetchone()
        self.assertNotEqual(row['api_key'], 'test-private-key')
        self.assertEqual(cipher().decrypt(row['api_key'].encode()), b'test-private-key')
        self.assertEqual(self.save(api_key='').status_code, 303)
        html = self.client.get('/ai').data
        self.assertNotIn(b'test-private-key', html)
        self.assertNotIn(row['api_key'].encode(), html)
        self.assertEqual(self.save(base_url='https://other.example', api_key='').status_code, 400)
        self.assertEqual(self.save(api_key='replacement-key').status_code, 303)

    def test_models_check(self):
        self.save()
        with patch('ai.httpx.get', return_value=httpx.Response(200, json={'data': [{'id': 'local-model'}]})) as get:
            result = self.client.post('/ai/openwebui/test', data={'csrf': self.csrf})
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'local-model', result.data)
        self.assertNotIn(b'test-private-key', result.data)
        self.assertEqual(get.call_args.args[0], 'http://openwebui:8080/api/models')
        self.assertFalse(get.call_args.kwargs['follow_redirects'])
        self.assertFalse(get.call_args.kwargs['verify'])
        self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer test-private-key')
        row = self.conn.execute("SELECT * FROM ai_connections WHERE provider='openwebui'").fetchone()
        self.assertEqual(row['status'], 'ok')
        self.assertIsNotNone(row['checked_at'])
        self.save()
        self.assertIsNone(self.conn.execute("SELECT checked_at FROM ai_connections WHERE provider='openwebui'").fetchone()['checked_at'])

    def test_failed_checks_never_expose_remote_body(self):
        self.save()
        for response in [httpx.Response(401, text='secret-response'), httpx.Response(302),
                         httpx.Response(500), httpx.Response(200, text='secret-response'),
                         httpx.Response(200, json={'wrong': []})]:
            with self.subTest(status=response.status_code), patch('ai.httpx.get', return_value=response):
                result = self.client.post('/ai/openwebui/test', data={'csrf': self.csrf})
                self.assertNotIn(b'secret-response', result.data)
                row = self.conn.execute("SELECT status FROM ai_connections WHERE provider='openwebui'").fetchone()
                self.assertEqual(row['status'], 'error')
        with patch('ai.httpx.get', side_effect=httpx.ConnectError('private info')):
            result = self.client.post('/ai/openwebui/test', data={'csrf': self.csrf})
            self.assertNotIn(b'private info', result.data)

    def test_csrf_and_url_validation(self):
        self.assertEqual(self.save(csrf='wrong').status_code, 400)
        self.assertEqual(self.client.post('/ai/codex/test').status_code, 400)
        for url in ['file:///etc/passwd', 'https://user:pass@server', 'http://server?key=secret', 'http://server:invalid']:
            with self.subTest(url=url):
                self.assertEqual(self.save(base_url=url).status_code, 400)
        self.assertEqual(validate_url('http://openwebui:8080/'), 'http://openwebui:8080')

    def test_codex_does_not_expose_output_or_generate(self):
        with patch('ai.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'private-token', 'private-email')) as run, \
                patch('ai.refresh_codex_models', return_value={'catalogue-model': ['low', 'high']}):
            result = self.client.post('/ai/codex/test', data={'csrf': self.csrf})
        self.assertNotIn(b'private-token', result.data)
        self.assertNotIn(b'private-email', result.data)
        self.assertEqual(run.call_args.args[0][-2:], ['login', 'status'])
        self.assertIn(b'catalogue-model', result.data)
        self.assertIn(b'catalogue-model', self.client.get('/ai').data)
        self.assertEqual(self.conn.execute("SELECT models FROM ai_connections WHERE provider='codex'").fetchone()['models'], ['catalogue-model'])
        for failure in [FileNotFoundError(), subprocess.TimeoutExpired('codex', 10)]:
            with patch('ai.subprocess.run', side_effect=failure), self.assertRaises(ValueError):
                check_codex()
        with patch('ai.subprocess.run', return_value=subprocess.CompletedProcess([], 1)), self.assertRaises(ValueError):
            check_codex()

    def test_codex_model_discovery_failure_is_visible(self):
        with patch('ai.check_codex'), patch('ai.refresh_codex_models', side_effect=ValueError('Codex model discovery timed out. Try again.')):
            result = self.client.post('/ai/codex/test', data={'csrf': self.csrf})
        self.assertIn(b'Codex model discovery timed out.', result.data)
        self.assertEqual(self.conn.execute("SELECT status FROM ai_connections WHERE provider='codex'").fetchone()['status'], 'error')

    def test_missing_and_corrupted_key(self):
        with patch('ai.httpx.get') as get:
            with self.assertRaises(ValueError):
                check_openwebui({'base_url': '', 'api_key': ''})
            with self.assertRaises(ValueError):
                check_openwebui({'base_url': 'https://example.com', 'api_key': 'corrupted'})
            get.assert_not_called()

    def test_real_http_connection(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append((self.path, self.headers.get('Authorization')))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"data": [{"id": "test-model"}]}')

            def log_message(self, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = {'base_url': f'http://127.0.0.1:{server.server_port}',
                          'api_key': cipher().encrypt(b'local-test-key').decode()}
            self.assertEqual(check_openwebui(connection), ['test-model'])
            self.assertEqual(received, [('/api/models', 'Bearer local-test-key')])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main(verbosity=2)
