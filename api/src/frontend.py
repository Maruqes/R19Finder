"""React page responses using the existing routes, sessions and validated actions."""
import json
import secrets
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from flask import g, current_app, get_flashed_messages, jsonify, render_template, request, session

FRONTEND = Path(__file__).resolve().parents[2] / 'frontend'
PRIVATE_KEYS = {'api_key', 'bot_token', 'owner', 'owner_hash', 'token', 'password'}


def public_data(value):
    if isinstance(value, dict):
        return {str(key): public_data(item) for key, item in value.items()
                if key not in PRIVATE_KEYS}
    if isinstance(value, (tuple, list, set)):
        return [public_data(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f'Unsupported frontend value: {type(value).__name__}')


def render_page(template, **context):
    # ZoneInfo is a server formatting helper; the client uses Intl explicitly.
    context.pop('lisbon', None)
    session.setdefault('csrf', secrets.token_urlsafe(32))
    g.style_nonce = secrets.token_urlsafe(24)
    payload = dict(nonce=g.style_nonce, page=template.removesuffix('.html'), data=public_data(context),
                   csrf=session['csrf'], messages=get_flashed_messages(),
                   path=request.path)
    if request.accept_mimetypes.best == 'application/json':
        response = jsonify(payload)
        response.headers['Cache-Control'] = 'no-store'
        response.vary.add('Accept')
        return response
    manifest_file = FRONTEND / 'static/app/.vite/manifest.json'
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text())
        entry = manifest['src/main.tsx']
    else:
        current_app.logger.error('React assets missing. Run npm ci && npm run build in frontend/.')
        return 'Frontend assets are missing. Build the frontend with npm ci && npm run build.', 503
    response = current_app.make_response(render_template('app.html', payload=payload, entry=entry))
    response.headers['Cache-Control'] = 'no-store'
    response.vary.add('Accept')
    return response
