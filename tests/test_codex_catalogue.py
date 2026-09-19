import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from codex_catalogue import list_models


class CatalogueTests(unittest.TestCase):
    def server(self, body):
        process = subprocess.Popen([sys.executable, '-u', '-c', body],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        return process

    def test_handshake_pagination_and_reasoning_without_generation(self):
        process = self.server('''
import json, sys
def receive(): return json.loads(sys.stdin.readline())
def reply(message): print(json.dumps(message), flush=True)
assert receive()['method'] == 'initialize'
reply({'id': 1, 'result': {}})
assert receive()['method'] == 'initialized'
for cursor, model, next_cursor in [(None, 'first', 'page2'), ('page2', 'second', None)]:
    request = receive()
    assert request['method'] == 'model/list'
    assert request['params']['cursor'] == cursor
    reply({'method': 'notification', 'params': {}})
    reply({'id': request['id'], 'result': {'data': [
        {'model': model, 'supportedReasoningEfforts': [{'reasoningEffort': 'high'}]},
        {'model': 'hidden', 'hidden': True}], 'nextCursor': next_cursor}})
sys.stdin.read()
''')
        with patch('codex_catalogue.subprocess.Popen', return_value=process):
            self.assertEqual(list_models(), {'first': ['high'], 'second': ['high']})
        self.assertIsNotNone(process.poll())

    def test_error_does_not_expose_cli_details(self):
        process = self.server("import sys; sys.stdin.readline(); print(" + repr(json.dumps(
            {'id': 1, 'error': {'message': 'private-account-details'}})) + ", flush=True); sys.stdin.read()")
        with patch('codex_catalogue.subprocess.Popen', return_value=process):
            with self.assertRaises(ValueError) as error:
                list_models()
        self.assertNotIn('private-account-details', str(error.exception))
        self.assertIsNotNone(process.poll())

    def test_timeout_terminates_server(self):
        process = self.server('import time; time.sleep(60)')
        with patch('codex_catalogue.subprocess.Popen', return_value=process):
            with self.assertRaisesRegex(ValueError, 'timed out'):
                list_models(timeout=0.05)
        self.assertIsNotNone(process.poll())

    def test_missing_cli(self):
        with patch('codex_catalogue.subprocess.Popen', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, 'Unable to read Codex models'):
                list_models()


if __name__ == '__main__':
    unittest.main(verbosity=2)
