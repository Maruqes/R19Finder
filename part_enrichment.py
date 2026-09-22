"""Tool-free structured completion for Open WebUI/Ollama part enrichment.

Uses the documented OpenAI-compatible /api/chat/completions endpoint. Sale
research retains its separate persisted, tool-enabled chat transport.
"""
import asyncio
import base64
import json
import time

import httpx

from ai import check_openwebui, cipher
from part_profile import enrichment_prompt, ENRICHMENT_SCHEMA


def run_openwebui_profile(job, photos, connection, is_cancelled, on_progress=None):
    if job['model'] not in check_openwebui(connection):
        raise ValueError('The selected model is no longer available. Refresh the model list.')
    if on_progress:
        on_progress('generating')
    key = cipher().decrypt(connection['api_key'].encode()).decode()
    content = [{'type': 'text', 'text': json.dumps(job['input'], ensure_ascii=False)}]
    for photo in photos:
        content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(photo['data']).decode()}})
    body = {'model': job['model'], 'stream': False,
            'messages': [{'role': 'system', 'content': enrichment_prompt(job['input']) +
                         '\nNo browsing tools are available in this fill. Use model knowledge only; state this limitation. Do not propose reference codes without browsing; ask the user to run Research exact identifiers. Return at most 30 suggestions to cover all selected languages.\nSchema:\n' + json.dumps(ENRICHMENT_SCHEMA)},
                         {'role': 'user', 'content': content}],
            'max_tokens': 6000,
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'part_profile', 'strict': True, 'schema': ENRICHMENT_SCHEMA}},
            'features': {'web_search': False, 'code_interpreter': False, 'image_generation': False, 'memory': False}}

    async def complete():
        async with httpx.AsyncClient(base_url=connection['base_url'].rstrip('/') + '/',
            headers={'Authorization': 'Bearer ' + key}, verify=False, follow_redirects=False,
            timeout=httpx.Timeout(300, connect=30)) as client:
            async with client.stream('POST', 'api/chat/completions', json=body) as response:
                if response.status_code in {401, 403}:
                    raise ValueError('Open WebUI denied access. Check the API key and chat completion permissions.')
                if response.status_code == 504:
                    raise ValueError('Open WebUI returned HTTP 504: its model service did not respond in time. Your draft is safe. Try later or choose another connection.')
                if response.status_code >= 300:
                    raise ValueError(f'Open WebUI returned HTTP {response.status_code}. Check model image and structured-output support.')
                # Some workspace configurations force streaming despite stream=false.
                if 'text/event-stream' in response.headers.get('content-type', ''):
                    pieces, size = [], 0
                    async for line in response.aiter_lines():
                        if not line.startswith('data:') or line[5:].strip() == '[DONE]':
                            continue
                        event = json.loads(line[5:])
                        for choice in event.get('choices', []):
                            text = choice.get('delta', {}).get('content', '')
                            if isinstance(text, str):
                                size += len(text)
                                if size > 131072:
                                    raise ValueError('Open WebUI returned an oversized response.')
                                pieces.append(text)
                    result = ''.join(pieces)
                else:
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 1048576:
                            raise ValueError('Open WebUI returned an oversized response.')
                        chunks.append(chunk)
                    data = json.loads(b''.join(chunks))
                    choices = data.get('choices', [])
                    result = choices[0].get('message', {}).get('content', '') if choices else ''
                if not isinstance(result, str) or not result.strip():
                    raise ValueError('Open WebUI returned no answer. Try a model with structured-output support.')
                return {'result': result}

    async def run():
        task = asyncio.create_task(complete())
        deadline = time.monotonic() + 300
        try:
            while not task.done():
                if is_cancelled():
                    raise ValueError('AI fill cancelled. The remote model may continue processing.')
                if time.monotonic() >= deadline:
                    raise ValueError('AI fill reached its five-minute limit. The remote model may continue processing.')
                await asyncio.wait({task}, timeout=1)
            return await task
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    return asyncio.run(run())
