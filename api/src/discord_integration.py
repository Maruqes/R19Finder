from frontend import render_page as render_template
"""Discord configuration, durable delivery and confirmed blacklist actions."""
from datetime import datetime, timedelta, timezone
import hashlib
import re
import uuid

from cryptography.fernet import InvalidToken
from flask import Blueprint, abort, flash, redirect, request, url_for
import httpx
from psycopg.types.json import Jsonb

from ai import cipher, validate_url
from listings import blacklist_part, listing_key, public_url

API = 'https://discord.com/api/v10'
SNOWFLAKE = re.compile(r'[0-9]{17,20}')


class DiscordError(ValueError):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


def read_token(config):
    try:
        return cipher().decrypt(config['bot_token'].encode()).decode()
    except (InvalidToken, OSError, ValueError, UnicodeError):
        raise DiscordError('Unable to read the bot token. Save it again.') from None


def api_request(config, method, path, payload=None):
    # The origin is fixed; tokens never go to a supplied URL or redirect.
    try:
        response = httpx.request(method, API + path,
            headers={'Authorization': 'Bot ' + read_token(config), 'User-Agent': 'R19Finder (Discord bot, 1.0)'},
            json=payload, timeout=12, follow_redirects=False)
    except httpx.RequestError:
        raise DiscordError('Discord is unreachable. Delivery will be retried.', retry_after=30) from None
    if response.status_code == 429:
        try:
            delay = max(1, min(3600, float(response.json()['retry_after'])))
        except (ValueError, KeyError, TypeError):
            delay = 60
        raise DiscordError('Discord rate limit. Delivery will be retried.', retry_after=delay)
    if response.status_code >= 500:
        raise DiscordError('Discord is temporarily unavailable.', retry_after=60)
    if response.status_code not in (200, 201, 204):
        messages = {401: 'Invalid bot token.', 403: 'The bot lacks permission in this channel.',
                    404: 'Channel or message not found. Check the channel ID and bot access.'}
        raise DiscordError(messages.get(response.status_code, f'Discord returned HTTP {response.status_code}.'))
    if response.status_code == 204:
        return {}
    try:
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise DiscordError('Discord returned an invalid response.', retry_after=30) from None


def check_connection(config):
    if not config['bot_token'] or not config['channel_id'] or not config['owner_id']:
        raise DiscordError('Save the bot token, channel ID and your user ID first.')
    user = api_request(config, 'GET', '/users/@me')
    if user.get('bot') is not True:
        raise DiscordError('Use a bot token, not a personal account token.')
    channel = api_request(config, 'GET', '/channels/' + config['channel_id'])
    if channel.get('type') != 0 or not channel.get('guild_id'):
        raise DiscordError('Choose a text channel in your Discord server.')
    return f"Bot verified. Channel: #{str(channel.get('name', 'channel'))[:100]}."


def text(value, limit):
    value = str(value or '').replace('@', '@\u200b')
    value = re.sub(r'([\\`*_~|<>\[\]])', r'\\\1', value)
    return value[:limit] or '—'


def listing_payload(config, job, index, listing):
    key = listing_key(listing['url'])
    embed = {'title': text(listing.get('title') or 'Part found', 200), 'url': listing['url'],
             'description': text(listing.get('description'), 500),
             'fields': [{'name': label, 'value': text(value, 200), 'inline': True} for label, value in (
                 ('Vehicle', job['vehicle'] or 'Not specified'), ('Price', listing.get('price') or 'Unconfirmed'),
                 ('Shipping', listing.get('shipping_cost') or 'Unconfirmed'),
                 ('Seller', listing.get('seller') or 'Unconfirmed'),
                 ('Location', listing.get('location') or 'Unconfirmed'),
                 ('Condition', listing.get('condition') or 'Unconfirmed'))],
             'footer': {'text': 'AI result. Verify price, availability and compatibility with the seller.'}}
    if public_url(listing.get('image_url'), image=True):
        embed['thumbnail'] = {'url': listing['image_url']}
    buttons = [{'type': 2, 'style': 4, 'label': 'Reject',
                'custom_id': f"r19:reject:{job['search_id']}:{index}"}]
    if len(listing['url']) <= 512:
        buttons.insert(0, {'type': 2, 'style': 5, 'label': 'View listing', 'url': listing['url']})
    if config['app_url'] and len(config['app_url']) < 440:
        buttons.append({'type': 2, 'style': 5, 'label': 'View request',
                        'url': f"{config['app_url']}/requests/{job['request_id']}#parts-found"})
    return {'content': f"<@{config['owner_id']}> New part · {text(job['description'], 220)}",
            'embeds': [embed], 'components': [{'type': 1, 'components': buttons}],
            'allowed_mentions': {'parse': [], 'users': [config['owner_id']]},
            'nonce': hashlib.sha256(f"{job['search_id']}:{key}".encode()).hexdigest()[:24], 'enforce_nonce': True}


def deliver_next(connect, expected_version=None):
    """Send at most one listing; persist progress and bounded retries independently of research."""
    with connect() as conn:
        if not conn.execute('SELECT pg_try_advisory_xact_lock(190021) AS locked').fetchone()['locked']:
            return False
        config = conn.execute('SELECT * FROM discord_settings WHERE id=1').fetchone()
        if not config['enabled'] or not config['bot_token'] or (expected_version is not None and config['version'] != expected_version):
            return False
        job = conn.execute('''SELECT n.*, s.request_id, s.schedule_id, s.vehicle, s.description, s.listings,
            s.discord_notify, s.status AS search_status, sc.discord_notify AS schedule_notify
            FROM discord_notifications n JOIN searches s ON s.id=n.search_id
            LEFT JOIN schedules sc ON sc.id=s.schedule_id
            WHERE n.status='pending' AND n.next_attempt <= now()
            ORDER BY n.next_attempt, n.created_at FOR UPDATE OF n SKIP LOCKED LIMIT 1''').fetchone()
        if not job:
            return False
        if job['search_status'] != 'completed' or not job['discord_notify'] or not job['schedule_notify']:
            conn.execute("UPDATE discord_notifications SET status='skipped', last_error='Notifications disabled or schedule removed.' WHERE search_id=%s", (job['search_id'],))
            return True
        blocked = {row['url_key'] for row in conn.execute('SELECT url_key FROM listing_blacklist WHERE request_id=%s', (job['request_id'],)).fetchall()}
        remaining = [(i, part) for i, part in enumerate(job['listings'])
                     if public_url(part.get('url')) and listing_key(part['url']) not in blocked
                     and listing_key(part['url']) not in job['messages']]
        if not remaining:
            conn.execute("UPDATE discord_notifications SET status=%s, last_error='', sent_at=now() WHERE search_id=%s",
                         ('sent' if job['messages'] else 'skipped', job['search_id']))
            return True
        index, part = remaining[0]
        try:
            result = api_request(config, 'POST', '/channels/' + config['channel_id'] + '/messages',
                                 listing_payload(config, job, index, part))
            message_id = str(result.get('id', ''))
            if not SNOWFLAKE.fullmatch(message_id):
                raise DiscordError('Discord did not confirm message delivery.', retry_after=30)
        except DiscordError as error:
            attempts = job['attempts'] + 1
            retry = error.retry_after is not None and attempts < 5
            conn.execute('''UPDATE discord_notifications SET status=%s, attempts=%s, last_error=%s,
                next_attempt=%s WHERE search_id=%s''',
                ('pending' if retry else 'failed', attempts, str(error),
                 datetime.now(timezone.utc) + timedelta(seconds=max(error.retry_after or 0, min(900, 15 * 2 ** attempts))), job['search_id']))
            return True
        messages = dict(job['messages'], **{listing_key(part['url']): {'id': message_id, 'channel_id': config['channel_id']}})
        conn.execute('''UPDATE discord_notifications SET messages=%s, status=%s, attempts=0, last_error='',
            next_attempt=now() + interval '2 seconds', sent_at=%s WHERE search_id=%s''',
            (Jsonb(messages), 'sent' if len(remaining) == 1 else 'pending',
             datetime.now(timezone.utc) if len(remaining) == 1 else None, job['search_id']))
        return True


def authorize(conn, user_id, channel_id):
    config = conn.execute('SELECT * FROM discord_settings WHERE id=1').fetchone()
    if not config['enabled'] or config['owner_id'] != str(user_id) or config['channel_id'] != str(channel_id):
        raise PermissionError('This command is restricted to the configured user and channel.')
    return config


def prepare_rejection(connect, user_id, channel_id, message_id, search_id, index):
    with connect() as conn:
        authorize(conn, user_id, channel_id)
        job = conn.execute('''SELECT s.*, n.messages FROM searches s
            JOIN discord_notifications n ON n.search_id=s.id WHERE s.id=%s''', (search_id,)).fetchone()
        if not job or job['status'] != 'completed' or not 0 <= index < len(job['listings']):
            raise ValueError('This part is no longer available.')
        part = job['listings'][index]
        delivery = job['messages'].get(listing_key(part['url']), {})
        if delivery.get('id') != str(message_id) or delivery.get('channel_id') != str(channel_id):
            raise ValueError('This message does not match this part.')
        if conn.execute('SELECT id FROM listing_blacklist WHERE request_id=%s AND url_key=%s',
                        (job['request_id'], listing_key(part['url']))).fetchone():
            raise ValueError('This part is already blacklisted for this request.')
        conn.execute('DELETE FROM discord_confirmations WHERE expires_at < now()')
        confirmation = conn.execute('''INSERT INTO discord_confirmations
            (search_id, listing_index, user_id, channel_id, message_id) VALUES (%s, %s, %s, %s, %s) RETURNING id''',
            (job['id'], index, str(user_id), str(channel_id), str(message_id))).fetchone()
        return str(confirmation['id']), part.get('title') or 'Part found'


def finish_rejection(connect, user_id, channel_id, confirmation_id, confirm):
    with connect() as conn:
        config = authorize(conn, user_id, channel_id)
        row = conn.execute('''SELECT * FROM discord_confirmations
            WHERE id=%s AND expires_at > now() AND used_at IS NULL FOR UPDATE''', (confirmation_id,)).fetchone()
        if not row or row['user_id'] != str(user_id) or row['channel_id'] != str(channel_id):
            raise ValueError('This confirmation has expired or was already used. Click Reject again.')
        job = conn.execute('SELECT * FROM searches WHERE id=%s', (row['search_id'],)).fetchone()
        if not job or not 0 <= row['listing_index'] < len(job['listings']):
            raise ValueError('This part is no longer available.')
        part = job['listings'][row['listing_index']]
        if confirm:
            blacklist_part(conn, job['request_id'], part['url'], 'Rejected on Discord.')
        conn.execute('UPDATE discord_confirmations SET used_at=now() WHERE id=%s', (row['id'],))
        return config, row['message_id']


def command_summary(connect, user_id, channel_id, command):
    with connect() as conn:
        authorize(conn, user_id, channel_id)
        if command == 'requests':
            rows = conn.execute('SELECT vehicle, description FROM requests ORDER BY created_at DESC LIMIT 10').fetchall()
            return '\n'.join(f"• {text(r['vehicle'] or 'No vehicle', 80)} — {text(r['description'], 90)}" for r in rows) or 'No requests.'
        rows = conn.execute('''SELECT s.*, r.vehicle FROM schedules s JOIN requests r ON r.id=s.request_id
            ORDER BY s.next_run LIMIT 10''').fetchall()
        days = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
        return '\n'.join(f"• {days[r['weekday']]} {r['local_time'].strftime('%H:%M')} · {text(r['vehicle'] or 'No vehicle', 80)} · "
                         f"{'Active' if r['enabled'] else 'Paused'} · Discord {'ON' if r['discord_notify'] else 'OFF'}" for r in rows) or 'No schedules.'


def create_discord_blueprint(connect, validate_csrf):
    bp = Blueprint('discord', __name__)

    def page(error=None, submitted=None):
        with connect() as conn:
            config = dict(conn.execute('SELECT * FROM discord_settings WHERE id=1').fetchone())
            deliveries = conn.execute('''SELECT n.*, s.vehicle FROM discord_notifications n
                JOIN searches s ON s.id=n.search_id ORDER BY n.created_at DESC LIMIT 20''').fetchall()
        config['has_token'] = bool(config.pop('bot_token'))
        config['online'] = bool(config['enabled'] and config['heartbeat_at'] and
                                config['heartbeat_at'] > datetime.now(timezone.utc) - timedelta(seconds=45))
        return render_template('discord.html', config=config, deliveries=deliveries, error=error, submitted=submitted or {})

    @bp.get('/discord')
    def settings():
        return page()

    @bp.post('/discord')
    def save():
        validate_csrf()
        values = {key: request.form.get(key, '').strip() for key in ('channel_id', 'owner_id', 'app_url')}
        enabled = request.form.get('enabled') == '1'
        token = request.form.get('bot_token', '').strip()
        try:
            if any(not SNOWFLAKE.fullmatch(values[key]) for key in ('channel_id', 'owner_id')):
                raise ValueError('Enter valid numeric channel and user IDs (17–20 digits).')
            if token and (not re.fullmatch(r'[A-Za-z0-9._-]{20,256}', token)):
                raise ValueError('Enter the bot token from the Discord Developer Portal.')
            values['app_url'] = validate_url(values['app_url']) if values['app_url'] else ''
            with connect() as conn:
                previous = conn.execute('SELECT * FROM discord_settings WHERE id=1 FOR UPDATE').fetchone()
                if not token and not previous['bot_token']:
                    raise ValueError('Enter a bot token.')
                encrypted = cipher().encrypt(token.encode()).decode() if token else previous['bot_token']
                conn.execute('''UPDATE discord_settings SET bot_token=%s, channel_id=%s, owner_id=%s,
                    app_url=%s, enabled=%s, version=version+1, status='saved', message='', checked_at=NULL,
                    heartbeat_at=NULL WHERE id=1''',
                    (encrypted, values['channel_id'], values['owner_id'], values['app_url'], enabled))
        except ValueError as error:
            return page(str(error), values), 400
        flash('Discord settings saved. The bot reconnects automatically.')
        return redirect(url_for('discord.settings'), code=303)

    @bp.post('/discord/test')
    def test():
        validate_csrf()
        with connect() as conn:
            config = conn.execute('SELECT * FROM discord_settings WHERE id=1').fetchone()
        try:
            message, status = check_connection(config), 'ok'
        except DiscordError as error:
            message, status = str(error), 'error'
        with connect() as conn:
            conn.execute('UPDATE discord_settings SET status=%s, message=%s, checked_at=now() WHERE id=1 AND version=%s',
                         (status, message, config['version']))
        return page()

    @bp.post('/discord/notifications/<uuid:search_id>/retry')
    def retry(search_id):
        validate_csrf()
        with connect() as conn:
            row = conn.execute("""UPDATE discord_notifications SET status='pending', attempts=0, next_attempt=now(), last_error=''
                WHERE search_id=%s AND status='failed' RETURNING search_id""", (search_id,)).fetchone()
            if not row:
                abort(404)
        flash('Delivery queued again. Already delivered pieces will not be resent.')
        return redirect(url_for('discord.settings'), code=303)

    return bp
