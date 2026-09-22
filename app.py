import hmac
import io
import os
import secrets
import uuid
import warnings
from markdown_it import MarkdownIt
from markupsafe import Markup

import psycopg
from psycopg.rows import dict_row
from PIL import Image, ImageOps, UnidentifiedImageError
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from ai import create_ai_blueprint, cached_codex_models
from discord_integration import create_discord_blueprint
from search import create_search_blueprint
from listings import public_url, listing_key, blacklist_part
from psycopg.types.json import Jsonb
from scheduling import DAYS, LISBON
from language_settings import create_settings_blueprint, get_preferences, LANGUAGES
from part_profile import FIELDS, GROUPS, FIELD_MAP, manual_profile
from part_drafts import create_part_blueprint
from cars import create_cars_blueprint, resolve_car, CAR_QUERY

app = Flask(__name__)
markdown = MarkdownIt('js-default', {'html': False, 'linkify': True}).disable('image')


@app.template_filter('markdown')
def render_markdown(value):
    # Raw HTML and images are disabled; the parser rejects unsafe URL schemes.
    return Markup(markdown.render(value or ''))


app.config.update(
    SECRET_KEY=os.environ['SECRET_KEY'],
    MAX_CONTENT_LENGTH=32 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)
Image.MAX_IMAGE_PIXELS = 20_000_000


def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, connect_timeout=5)


@app.context_processor
def csrf_context():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return {'csrf_token': session['csrf']}


@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: https:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


@app.get('/')
def index():
    page = max(1, request.args.get('page', 1, type=int))
    query = request.args.get('q', '').strip()[:200]
    pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    with connect() as conn:
        request_count = conn.execute('SELECT count(*) AS total FROM requests').fetchone()['total']
        total = conn.execute('SELECT count(*) AS total FROM requests WHERE vehicle ILIKE %s OR description ILIKE %s',
                             (pattern, pattern)).fetchone()['total']
        active_count = conn.execute("SELECT count(*) AS n FROM searches WHERE status IN ('queued', 'running')").fetchone()['n']
        cars = conn.execute(CAR_QUERY + ' ORDER BY name, id').fetchall()
        orders = conn.execute('''SELECT r.*, (SELECT count(*) FROM photos p WHERE p.request_id=r.id) AS photo_count,
            (SELECT id FROM photos p WHERE p.request_id=r.id ORDER BY position LIMIT 1) AS cover_id,
            (SELECT status FROM searches s WHERE s.request_id=r.id ORDER BY s.created_at DESC, s.id DESC LIMIT 1) AS latest_status
            FROM requests r WHERE vehicle ILIKE %s OR description ILIKE %s
            ORDER BY created_at DESC, id LIMIT 12 OFFSET %s''', (pattern, pattern, (page - 1) * 12)).fetchall()
    return render_template('index.html', orders=orders, total=total, page=page, cars=cars,
                           query=query, request_count=request_count, active_count=active_count)


def normalize_photo(upload, max_bytes=5 * 1024 * 1024):
    data = upload.read() if max_bytes is None else upload.read(max_bytes + 1)
    if max_bytes is not None and len(data) > max_bytes:
        raise ValueError('Each photo must be no larger than 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ValueError('Use JPG, PNG or WebP photos.')
                original.load()
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((2000, 2000))
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=85)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('One of the photos is invalid or its resolution is too high.') from None


def validate_csrf():
    if 'csrf' not in session or not hmac.compare_digest(session['csrf'].encode(), request.form.get('csrf', '').encode()):
        abort(400, description='The form has expired. Refresh the page and try again.')


app.register_blueprint(create_settings_blueprint(lambda: connect(), validate_csrf))
app.register_blueprint(create_part_blueprint(lambda: connect(), validate_csrf, normalize_photo))
app.register_blueprint(create_ai_blueprint(lambda: connect(), validate_csrf))
app.register_blueprint(create_discord_blueprint(lambda: connect(), validate_csrf))
app.register_blueprint(create_search_blueprint(lambda: connect(), validate_csrf))
app.register_blueprint(create_cars_blueprint(lambda: connect(), validate_csrf,
    lambda upload: normalize_photo(upload, max_bytes=None)))


def request_form(**context):
    with connect() as conn:
        context['cars'] = conn.execute('SELECT id, name FROM cars ORDER BY name, id').fetchall()
        context['language_preferences'] = get_preferences(conn)
        context['language_names'] = LANGUAGES
        context['part_models'] = conn.execute("SELECT models FROM ai_connections WHERE provider='openwebui'").fetchone()['models']
    order = context.get('order') or {}
    context['selected_car_id'] = (request.form.get('car_id', '') if request.method == 'POST'
                                  else str(order.get('car_id') or request.args.get('car_id', '')))
    context.update(part_fields=FIELDS, part_groups=GROUPS, part_codex_models=cached_codex_models())
    context['part_profile'] = context.get('part_profile', order.get('part_profile', {}))
    if request.method == 'POST' and 'part_profile' not in request.form:
        # Re-render even invalid values so a validation error never erases typed details.
        context['part_profile'] = {'facts': [dict(id=str(uuid.uuid4()), field=key, value=value)
            for key in FIELD_MAP for value in request.form.getlist('part_' + key) if value.strip()]}
    return render_template('new.html', **context)


def validate_fields(description, vehicle):
    if not 10 <= len(description) <= 5000:
        raise ValueError('The description must contain between 10 and 5000 characters.')
    if len(vehicle) > 120:
        raise ValueError('The vehicle field must contain no more than 120 characters.')


@app.post('/requests')
def create_request():
    validate_csrf()
    description = request.form.get('description', '').strip()
    vehicle = request.form.get('vehicle', '').strip()
    uploads = [f for f in request.files.getlist('photos') if f.filename]
    try:
        validate_fields(description, vehicle)
        profile = manual_profile(request.form)
        if len(uploads) > 6:
            raise ValueError('Add up to 6 photos per request.')
        photos = [normalize_photo(upload) for upload in uploads]
        with connect() as conn:
            car = resolve_car(conn, request.form.get('car_id', ''))
    except ValueError as error:
        return request_form(error=str(error), description=description, vehicle=vehicle), 400
    order_id = uuid.uuid4()
    with connect() as conn:
        conn.execute('INSERT INTO requests (id, description, vehicle, car_id, part_profile) VALUES (%s, %s, %s, %s, %s)',
                     (order_id, description, car['name'] if car else vehicle, car['id'] if car else None, Jsonb(profile)))
        for position, data in enumerate(photos):
            conn.execute('INSERT INTO photos (id, request_id, content_type, data, position) VALUES (%s, %s, %s, %s, %s)',
                         (uuid.uuid4(), order_id, 'image/jpeg', data, position))
    flash('Request saved. You can now view its details.')
    return redirect(url_for('detail', order_id=order_id), code=303)


@app.get('/requests/new')
def new_request():
    return request_form()


@app.route('/requests/<uuid:order_id>/edit', methods=['GET', 'POST'])
def edit_request(order_id):
    if request.method == 'POST':
        validate_csrf()
    with connect() as conn:
        # Serialize edits so simultaneous uploads cannot exceed the photo limit.
        order = conn.execute('SELECT * FROM requests WHERE id=%s FOR UPDATE', (order_id,)).fetchone()
        if not order:
            abort(404)
        photos = conn.execute('SELECT id FROM photos WHERE request_id=%s ORDER BY position', (order_id,)).fetchall()
        if request.method == 'GET':
            return request_form(order=order, photos=photos,
                                   description=order['description'], vehicle=order['vehicle'])
        description = request.form.get('description', '').strip()
        vehicle = request.form.get('vehicle', '').strip()
        removed = set(request.form.getlist('remove_photos'))
        uploads = [f for f in request.files.getlist('photos') if f.filename]
        remaining = [photo for photo in photos if str(photo['id']) not in removed]
        try:
            validate_fields(description, vehicle)
            profile = manual_profile(request.form, order.get('part_profile', {}))
            if request.form.get('profile_revision') is not None and request.form['profile_revision'] != str(order['profile_revision']):
                raise ValueError('This part changed in another tab. Reload before editing.')
            car = resolve_car(conn, request.form.get('car_id', ''))
            if not removed.issubset({str(photo['id']) for photo in photos}):
                raise ValueError('One of the photos no longer belongs to this request. Refresh the page.')
            if len(remaining) + len(uploads) > 6:
                raise ValueError('A request can have up to 6 photos. Remove some before adding more.')
            new_photos = [normalize_photo(upload) for upload in uploads]
        except ValueError as error:
            return request_form(order=order, photos=photos, removed=removed,
                                   description=description, vehicle=vehicle, error=str(error)), 400
        conn.execute('UPDATE requests SET description=%s, vehicle=%s, car_id=%s, part_profile=%s, profile_revision=profile_revision+1 WHERE id=%s',
                     (description, car['name'] if car else vehicle, car['id'] if car else None, Jsonb(profile), order_id))
        for photo in photos:
            if str(photo['id']) in removed:
                conn.execute('DELETE FROM photos WHERE id=%s AND request_id=%s', (photo['id'], order_id))
        for position, photo in enumerate(remaining):
            conn.execute('UPDATE photos SET position=%s WHERE id=%s', (position, photo['id']))
        for position, data in enumerate(new_photos, start=len(remaining)):
            conn.execute('INSERT INTO photos (id, request_id, content_type, data, position) VALUES (%s, %s, %s, %s, %s)',
                         (uuid.uuid4(), order_id, 'image/jpeg', data, position))
    flash('Request updated.')
    return redirect(url_for('detail', order_id=order_id), code=303)


@app.get('/requests/<uuid:order_id>')
def detail(order_id):
    with connect() as conn:
        order = conn.execute('SELECT * FROM requests WHERE id=%s', (order_id,)).fetchone()
        if not order:
            abort(404)
        photos = conn.execute('SELECT id FROM photos WHERE request_id=%s ORDER BY position', (order_id,)).fetchall()
        searches = conn.execute('SELECT * FROM searches WHERE request_id=%s ORDER BY created_at DESC', (order_id,)).fetchall()
        blacklist = conn.execute('SELECT * FROM listing_blacklist WHERE request_id=%s ORDER BY created_at DESC', (order_id,)).fetchall()
        schedules = conn.execute('SELECT * FROM schedules WHERE request_id=%s ORDER BY weekday, local_time', (order_id,)).fetchall()
        discord_config = conn.execute("SELECT enabled, bot_token != '' AS configured FROM discord_settings WHERE id=1").fetchone()
        connection = conn.execute("SELECT models FROM ai_connections WHERE provider='openwebui'").fetchone()
        car = conn.execute('SELECT * FROM cars WHERE id=%s', (order['car_id'],)).fetchone() if order['car_id'] else None
    found_parts, seen_urls = [], {item['url_key'] for item in blacklist}
    for search in searches:
        if search['status'] != 'completed':
            continue
        for listing in search['listings']:
            if listing.get('url') and listing_key(listing['url']) not in seen_urls:
                seen_urls.add(listing_key(listing['url']))
                found_parts.append(dict(listing, found_at=search['finished_at'] or search['created_at'],
                                       provider=search['provider']))
    return render_template('detail.html', part_field_map=FIELD_MAP, order=order, photos=photos, searches=searches, found_parts=found_parts, blacklist=blacklist,
                           models=connection['models'], codex_models=cached_codex_models(), schedules=schedules, weekdays=DAYS, lisbon=LISBON, car=car,
                           discord_config=discord_config, active_search=any(s['status'] in {'queued', 'running'} for s in searches))


@app.post('/requests/<uuid:order_id>/blacklist')
def blacklist_listing(order_id):
    validate_csrf()
    url = public_url(request.form.get('url', ''))
    reason = request.form.get('reason', '').strip()
    if not url or len(reason) > 500:
        abort(400)
    with connect() as conn:
        try:
            blacklist_part(conn, order_id, url, reason)
        except LookupError:
            abort(404)
    flash('Listing removed from Parts Found and blacklisted for this request.')
    return redirect(url_for('detail', order_id=order_id, _anchor='parts-found'), code=303)


@app.post('/requests/<uuid:order_id>/blacklist/<uuid:entry_id>/restore')
def restore_listing(order_id, entry_id):
    validate_csrf()
    with connect() as conn:
        deleted = conn.execute('DELETE FROM listing_blacklist WHERE id=%s AND request_id=%s RETURNING id',
                               (entry_id, order_id)).fetchone()
        if not deleted:
            abort(404)
    flash('Listing restored to Parts Found. Future searches will look for other listings.')
    return redirect(url_for('detail', order_id=order_id, _anchor='parts-found'), code=303)


@app.get('/photos/<uuid:photo_id>')
def photo(photo_id):
    with connect() as conn:
        photo = conn.execute('SELECT data, content_type FROM photos WHERE id=%s', (photo_id,)).fetchone()
    if not photo:
        abort(404)
    return send_file(io.BytesIO(photo['data']), mimetype=photo['content_type'], max_age=86400)


@app.route('/websites', methods=['GET', 'POST'])
def websites():
    if request.method == 'POST':
        validate_csrf()
        submitted = request.form.get('urls', '')
        urls = list(dict.fromkeys(line.strip().rstrip('/') for line in submitted.splitlines() if line.strip()))
        if len(submitted) > 65000 or len(urls) > 30 or any(not public_url(url) for url in urls):
            return render_template('websites.html', urls=submitted,
                error='Use up to 30 public HTTP/HTTPS URLs, one per line, without credentials.'), 400
        with connect() as conn:
            conn.execute('UPDATE website_settings SET urls=%s WHERE id=1', (Jsonb(urls),))
        flash('Website list saved. New searches will use this order.')
        return redirect(url_for('websites'), code=303)
    with connect() as conn:
        row = conn.execute('SELECT urls FROM website_settings WHERE id=1').fetchone()
    return render_template('websites.html', urls='\n'.join(row['urls']))


@app.get('/health')
def health():
    with connect() as conn:
        conn.execute('SELECT 1 FROM requests LIMIT 1')
    return {'status': 'ok'}


@app.errorhandler(413)
def too_large(error):
    return render_template('error.html', message='The upload exceeds 32 MB. Upload fewer photos at a time.'), 413


@app.errorhandler(400)
@app.errorhandler(404)
def client_error(error):
    message = error.description if error.code == 400 else 'This page or request could not be found.'
    return render_template('error.html', message=message), error.code


@app.errorhandler(psycopg.Error)
def database_error(error):
    app.logger.exception('Database operation failed')
    return render_template('error.html', message='Unable to access requests. Try again shortly.'), 503
