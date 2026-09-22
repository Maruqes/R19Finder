"""Security and transport boundaries for server-backed React pages."""
import unittest
from datetime import datetime, timezone
from uuid import UUID

from app import app
from frontend import public_data, render_page
from page_payload import page_data


class FrontendTransportTests(unittest.TestCase):
    def test_bootstrap_escapes_script_delimiters(self):
        with app.test_request_context('/'):
            response = render_page('index.html', description='</script><script>alert(1)</script>')
            html = response.get_data(as_text=True)
            self.assertNotIn('</script><script>alert', html)
            self.assertEqual(page_data(response)['description'], '</script><script>alert(1)</script>')
            self.assertIn('no-store', response.headers['Cache-Control'])

    def test_json_excludes_credentials_and_encodes_database_types(self):
        with app.test_request_context('/ai', headers={'Accept': 'application/json'}):
            response = render_page('ai.html', connections={'codex': {'api_key': 'secret', 'has_key': True}},
                                   config={'bot_token': 'secret-bot', 'has_token': True},
                                   id=UUID('11111111-1111-4111-8111-111111111111'),
                                   checked_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            self.assertNotIn('secret', response.get_data(as_text=True))
            self.assertTrue(response.json['data']['connections']['codex']['has_key'])
            self.assertTrue(response.json['data']['config']['has_token'])
            self.assertEqual(response.json['data']['id'], '11111111-1111-4111-8111-111111111111')
            self.assertEqual(response.json['data']['checked_at'], '2026-01-01T00:00:00+00:00')
            self.assertIn('Accept', response.headers['Vary'])

    def test_each_response_has_a_fresh_style_nonce(self):
        nonces=[]
        for _ in range(2):
            with app.test_request_context('/', headers={'Accept': 'application/json'}):
                response=render_page('index.html')
                response=app.process_response(response)
                nonce=response.json['nonce']
                nonces.append(nonce)
                self.assertIn(f"style-src 'self' 'nonce-{nonce}'", response.headers['Content-Security-Policy'])
                self.assertNotIn('unsafe-inline', response.headers['Content-Security-Policy'])
        self.assertNotEqual(*nonces)

    def test_unknown_objects_fail_closed_instead_of_stringifying_secrets(self):
        with self.assertRaises(TypeError):
            public_data({'unexpected': object()})
