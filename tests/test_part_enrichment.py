import json
import unittest
from unittest.mock import Mock, patch

import httpx
from part_enrichment import run_openwebui_profile


class StructuredTransportTests(unittest.TestCase):
    def run_transport(self, handler, cancelled=lambda: False):
        client_type = httpx.AsyncClient
        connection = dict(base_url='http://openwebui.test', api_key='encrypted')
        job = dict(model='local-model', input={'description': 'A left rear tail lamp'})
        with patch('part_enrichment.check_openwebui', return_value=['local-model']), \
             patch('part_enrichment.cipher', return_value=Mock(decrypt=Mock(return_value=b'test-token'))), \
             patch('part_enrichment.httpx.AsyncClient', side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw)):
            return run_openwebui_profile(job, [], connection, cancelled)

    def test_structured_completion_without_research_tools(self):
        def handler(request):
            payload = json.loads(request.content)
            self.assertEqual(request.url.path, '/api/chat/completions')
            self.assertFalse(payload['features']['web_search'])
            self.assertFalse(payload['stream'])
            self.assertEqual(payload['response_format']['type'], 'json_schema')
            self.assertNotIn('chat_id', payload)
            return httpx.Response(200, json={'choices': [{'message': {'content': '{"suggestions":[]}'}}]})
        self.assertEqual(self.run_transport(handler)['result'], '{"suggestions":[]}')

    def test_forced_stream_does_not_include_reasoning(self):
        def handler(request):
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text='data: {"choices":[{"delta":{"reasoning_content":"private reasoning","content":"{\\"suggestions\\":[]}"}}]}\n\ndata: [DONE]\n\n')
        self.assertEqual(self.run_transport(handler)['result'], '{"suggestions":[]}')

    def test_denial_and_empty_output_are_recoverable(self):
        for response in (httpx.Response(403), httpx.Response(200, json={'choices': []})):
            with self.assertRaises(ValueError):
                self.run_transport(lambda request: response)

    def test_cancelled_job_does_not_start_generation(self):
        handler = Mock()
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            self.run_transport(handler, lambda: True)
        handler.assert_not_called()


if __name__ == '__main__':
    unittest.main()
