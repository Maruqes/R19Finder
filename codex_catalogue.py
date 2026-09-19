"""Read Codex's model catalogue without starting a thread or generating a response."""
import json
import os
import selectors
import subprocess
import time


def list_models(timeout=20):
    process = None
    try:
        process = subprocess.Popen(
            ['codex', '-c', 'cli_auth_credentials_store="file"', 'app-server'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + timeout
        pending = b''
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)

            def send(message):
                process.stdin.write((json.dumps(message) + '\n').encode())
                process.stdin.flush()

            def response(request_id):
                nonlocal pending
                while time.monotonic() < deadline:
                    if b'\n' not in pending:
                        if not selector.select(max(0, deadline - time.monotonic())):
                            break
                        chunk = os.read(process.stdout.fileno(), 65536)
                        if not chunk:
                            raise ValueError('Codex closed the model connection. Try again.')
                        pending += chunk
                        continue
                    line, pending = pending.split(b'\n', 1)
                    message = json.loads(line)
                    if message.get('id') != request_id:
                        continue
                    if 'error' in message:
                        raise ValueError('Codex could not list models. Check authentication and try again.')
                    return message['result']
                raise ValueError('Codex model discovery timed out. Try again.')

            send({'id': 1, 'method': 'initialize', 'params': {
                'clientInfo': {'name': 'r19finder', 'version': '1.0.0'}}})
            response(1)
            send({'method': 'initialized', 'params': {}})
            models, cursor, seen = {}, None, set()
            request_id = 2
            while True:
                send({'id': request_id, 'method': 'model/list', 'params': {
                    'limit': 100, 'includeHidden': False, 'cursor': cursor}})
                result = response(request_id)
                for model in result['data']:
                    if not model.get('hidden', False):
                        models[model['model']] = [
                            level['reasoningEffort'] for level in model.get('supportedReasoningEfforts', [])]
                cursor = result.get('nextCursor')
                if not cursor:
                    return models
                if cursor in seen:
                    raise ValueError('Codex returned an invalid model list. Try again.')
                seen.add(cursor)
                request_id += 1
    except (OSError, KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError):
        # Raw errors and CLI output can contain account details.
        raise ValueError('Unable to read Codex models. Check the CLI installation and authentication.') from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdin.close()
            process.stdout.close()
