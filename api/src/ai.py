"""Configuration and read-only connection checks. No model generation is performed."""
from frontend import render_page as render_template
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, abort, flash, redirect, request, url_for
import httpx
from psycopg.types.json import Jsonb
from codex_catalogue import list_models

SECRET_FILE = Path(os.environ.get('APP_SECRET_DIR', '/home/app/.local/share/r19finder')) / 'encryption.key'


def create_secret_key():
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, 'wb') as file:
        file.write(Fernet.generate_key())


def cipher():
    return Fernet(SECRET_FILE.read_bytes())


def validate_url(value):
    value = value.strip().rstrip('/')
    try:
        parts = urlsplit(value)
        port = parts.port
        valid = (parts.scheme in {'http', 'https'} and parts.hostname
                 and not parts.username and not parts.password
                 and not parts.query and not parts.fragment
                 and (port is None or 1 <= port <= 65535))
    except ValueError:
        valid = False
    if not valid or len(value) > 2048 or any(c.isspace() for c in value):
        raise ValueError('Enter a valid HTTP or HTTPS URL without credentials, query parameters or fragments.')
    return value


def check_openwebui(connection):
    if not connection['base_url'] or not connection['api_key']:
        raise ValueError('Save the URL and API key before testing.')
    try:
        key = cipher().decrypt(connection['api_key'].encode()).decode()
    except (InvalidToken, OSError, ValueError):
        raise ValueError('Unable to read the saved key. Enter the API key again.') from None
    try:
        response = httpx.get(
            connection['base_url'] + '/api/models',
            headers={'Authorization': f'Bearer {key}'},
            # This Open WebUI connection runs on the private VPN with a local CA.
            timeout=None, follow_redirects=False, verify=False,
        )
        if response.status_code in {401, 403}:
            raise ValueError('Access denied. Check the API key and permission for /api/models in Open WebUI.')
        if 300 <= response.status_code < 400:
            raise ValueError('The address redirects to another URL. Save the final Open WebUI address.')
        if response.status_code != 200:
            raise ValueError(f'Open WebUI returned HTTP {response.status_code}. Check the URL and service.')
        payload = response.json()
        models = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(models, list) or any(not isinstance(m, dict) or not isinstance(m.get('id'), str) for m in models):
            raise ValueError('The response does not contain a valid model list. Check that the URL points to Open WebUI.')
        return [model['id'] for model in models]
    except httpx.TimeoutException:
        raise ValueError('Open WebUI timed out. Check the address and try again.') from None
    except httpx.RequestError:
        raise ValueError('Unable to reach Open WebUI. Check the URL and network connection.') from None
    except json.JSONDecodeError:
        raise ValueError('The address did not return JSON. Check the Open WebUI URL.') from None
    except (TypeError, UnicodeError):
        raise ValueError('Open WebUI returned an invalid response.') from None


_codex_catalogue = {}
_codex_checked_at = float('-inf')


def refresh_codex_models():
    global _codex_catalogue, _codex_checked_at
    _codex_catalogue = list_models()
    _codex_checked_at = time.monotonic()
    return _codex_catalogue


def cached_codex_models():
    """Read only the public model catalogue, never the CLI credentials."""
    global _codex_catalogue, _codex_checked_at
    if time.monotonic() - _codex_checked_at < 60:
        return _codex_catalogue
    try:
        return refresh_codex_models()
    except ValueError:
        _codex_checked_at = time.monotonic()
    if _codex_catalogue:
        return _codex_catalogue
    try:
        payload = json.loads(Path('/home/app/.codex/models_cache.json').read_text())
        _codex_catalogue = {
            model['slug']: [level['effort'] for level in model.get('supported_reasoning_levels', [])
                            if isinstance(level, dict) and level.get('effort') in
                            {'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}]
            for model in payload['models']
            if isinstance(model, dict) and model.get('visibility') == 'list'
            and isinstance(model.get('slug'), str) and model['slug']}
        return _codex_catalogue
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def check_codex():
    try:
        result = subprocess.run(
            ['codex', '-c', 'cli_auth_credentials_store="file"', 'login', 'status'],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except FileNotFoundError:
        raise ValueError('Codex CLI is not installed. Rebuild the application with make up.') from None
    except subprocess.TimeoutExpired:
        raise ValueError('Codex CLI timed out. Try again.') from None
    except OSError:
        raise ValueError('Unable to run Codex CLI.') from None
    if result.returncode != 0:
        raise ValueError('Codex CLI is not authenticated. Run make codex-login in the terminal.')
    # Never return raw CLI output: it may include account or credential details.
    return 'Local authentication found. This test does not validate the account online or generate responses.'


def create_ai_blueprint(connect, validate_csrf):
    bp = Blueprint('ai', __name__)

    def page(error=None, models=None, submitted_url=None):
        with connect() as conn:
            rows = conn.execute('SELECT * FROM ai_connections').fetchall()
        connections = {row['provider']: dict(row) for row in rows}
        # Never send encrypted or plaintext credentials into template context.
        for connection in connections.values():
            connection['has_key'] = bool(connection.pop('api_key'))
        return render_template('ai.html', connections=connections, error=error,
                               models=models, submitted_url=submitted_url)

    @bp.get('/ai')
    def settings():
        return page()

    @bp.post('/ai/openwebui')
    def save_openwebui():
        validate_csrf()
        try:
            base_url = validate_url(request.form.get('base_url', ''))
            key = request.form.get('api_key', '').strip()
            if key and (len(key) > 4096 or not key.isascii() or any(c.isspace() for c in key)):
                raise ValueError('The API key has an invalid format.')
            with connect() as conn:
                previous = conn.execute("SELECT * FROM ai_connections WHERE provider='openwebui' FOR UPDATE").fetchone()
                if not key and (not previous['api_key'] or previous['base_url'] != base_url):
                    raise ValueError('Enter the API key. When changing the URL, enter the key for that server again.')
                encrypted = cipher().encrypt(key.encode()).decode() if key else previous['api_key']
                conn.execute("""UPDATE ai_connections SET base_url=%s, api_key=%s,
                    status='untested', message='', checked_at=NULL, models='[]' WHERE provider='openwebui'""", (base_url, encrypted))
        except ValueError as error:
            return page(error=str(error), submitted_url=request.form.get('base_url', '')), 400
        flash('Open WebUI settings saved. You can now test the connection.')
        return redirect(url_for('ai.settings'), code=303)

    @bp.post('/ai/<provider>/test')
    def test_connection(provider):
        validate_csrf()
        if provider not in {'openwebui', 'codex'}:
            abort(404)
        with connect() as conn:
            connection = conn.execute('SELECT * FROM ai_connections WHERE provider=%s', (provider,)).fetchone()
        models = None
        try:
            if provider == 'codex':
                check_codex()
                models = list(refresh_codex_models())
                message = f'Local authentication found. {len(models)} model(s) listed by Codex. No response was generated.'
            else:
                models = check_openwebui(connection)
                message = f'Connection confirmed. {len(models)} model(s) available. No response was generated.'
            status = 'ok'
        except ValueError as error:
            message, status = str(error), 'error'
        with connect() as conn:
            conn.execute('''UPDATE ai_connections SET status=%s, message=%s, checked_at=now()
                WHERE provider=%s AND base_url=%s AND api_key=%s''',
                (status, message, provider, connection['base_url'], connection['api_key']))
            if models is not None:
                conn.execute('''UPDATE ai_connections SET models=%s WHERE provider=%s AND base_url=%s AND api_key=%s''',
                             (Jsonb(models), provider, connection['base_url'], connection['api_key']))
        return page(models=models)

    return bp
