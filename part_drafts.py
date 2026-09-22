"""Session-owned drafts and asynchronous enrichment, separate from sale searches."""
import json
import hashlib
import secrets
import uuid

from flask import Blueprint, abort, jsonify, request, session, url_for
from psycopg.types.json import Jsonb
from werkzeug.exceptions import HTTPException

from ai import cached_codex_models
from cars import resolve_car
from language_settings import get_preferences
from enrichment_progress import progress_for
from part_profile import validate_profile


def create_part_blueprint(connect, validate_csrf, normalize_photo):
    bp = Blueprint('parts', __name__)

    @bp.after_request
    def no_cache(response):
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @bp.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 422

    @bp.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    def owner():
        if 'part_owner' not in session:
            session['part_owner'] = secrets.token_urlsafe(32)
        return hashlib.sha256(session['part_owner'].encode()).hexdigest()

    def owned(conn, draft_id, lock=False):
        draft = conn.execute('SELECT * FROM part_drafts WHERE id=%s AND owner=%s AND updated_at > now() - interval \'7 days\'' + (' FOR UPDATE' if lock else ''),
                             (draft_id, owner())).fetchone()
        if not draft:
            abort(404)
        return draft

    def revision(draft):
        if str(draft['revision']) != request.form.get('revision'):
            abort(409, description='This draft changed in another tab. Reload it before saving.')
        if draft['created_request_id']:
            abort(409, description='This draft has already been saved.')

    def payload(conn, draft):
        photos = conn.execute('SELECT id FROM part_draft_photos WHERE draft_id=%s ORDER BY position', (draft['id'],)).fetchall()
        run = conn.execute('SELECT id, status, provider, model, reasoning_effort FROM part_enrichments WHERE draft_id=%s ORDER BY created_at DESC LIMIT 1', (draft['id'],)).fetchone()
        return dict(id=str(draft['id']), revision=draft['revision'], content=draft['content'],
                    request_id=str(draft['request_id'] or ''),
                    saved_url=url_for('detail', order_id=draft['created_request_id']) if draft['created_request_id'] else None,
                    photos=[dict(id=str(p['id']), url=url_for('parts.photo', draft_id=draft['id'], photo_id=p['id'])) for p in photos],
                    run=dict(id=str(run['id']), status=run['status'], provider=run['provider'], model=run['model'], reasoning_effort=run['reasoning_effort']) if run else None)

    def update_content(conn, draft):
        description = request.form.get('description', '').strip()
        vehicle = request.form.get('vehicle', '').strip()
        if not 10 <= len(description) <= 5000 or len(vehicle) > 120:
            raise ValueError('Use a description of 10–5000 characters and a vehicle of up to 120 characters.')
        car = resolve_car(conn, request.form.get('car_id', ''))
        profile = validate_profile(request.form.get('part_profile', '{}'))
        raw_review = request.form.get('review_state', '{}')
        if len(raw_review) > 131072:
            raise ValueError('Review state is too large.')
        try:
            review = json.loads(raw_review)
        except ValueError:
            raise ValueError('Invalid review state.') from None
        if not isinstance(review, dict) or set(review) - {'pending', 'handled', 'undo'}:
            raise ValueError('Invalid review state.')
        if not isinstance(review.get('pending', []), list) or len(review.get('pending', [])) > 60:
            raise ValueError('Too many pending suggestions.')
        pending = []
        for fact in review.get('pending', []):
            checked = validate_profile({'facts': [fact]})['facts']
            if not checked:
                raise ValueError('A pending suggestion cannot be empty.')
            pending.extend(checked)
        review['pending'] = pending
        if not isinstance(review.get('handled', []), list) or len(review.get('handled', [])) > 200:
            raise ValueError('Too many review decisions.')
        if any(not isinstance(item, str) for item in review.get('handled', [])):
            raise ValueError('Invalid review decision.')
        review['handled'] = [str(uuid.UUID(item)) for item in review.get('handled', [])]
        # Undo is a bounded client snapshot; it is never applied by the server.
        if not isinstance(review.get('undo', []), list) or len(review.get('undo', [])) > 60:
            raise ValueError('Invalid undo state.')
        content = dict(description=description, vehicle=car['name'] if car else vehicle,
                       car_id=str(car['id']) if car else '', car_profile=dict(car['specs'], name=car['name']) if car else {},
                       profile_revision=draft['content'].get('profile_revision', 0), part_profile=profile, review_state=review)
        # Changing the vehicle invalidates previously accepted AI fitment claims.
        if draft['content'].get('car_id', '') != content['car_id'] or draft['content'].get('vehicle', '') != content['vehicle'] or (draft['content'].get('car_profile') is not None and draft['content']['car_profile'] != content['car_profile']):
            for fact in profile['facts']:
                if fact['origin'] == 'ai':
                    fact.update(review_status='pending', verification_status='unverified')
        existing = conn.execute('SELECT id FROM part_draft_photos WHERE draft_id=%s ORDER BY position', (draft['id'],)).fetchall()
        removed = set(request.form.getlist('remove_draft_photos'))
        if not removed.issubset({str(p['id']) for p in existing}):
            raise ValueError('Invalid draft photo selection.')
        retained = [p for p in existing if str(p['id']) not in removed]
        uploads = [f for f in request.files.getlist('photos') if f.filename]
        if len(retained) + len(uploads) > 6:
            raise ValueError('Add up to six photos in total.')
        images = [normalize_photo(f) for f in uploads]
        for photo in existing:
            if str(photo['id']) in removed:
                conn.execute('DELETE FROM part_draft_photos WHERE id=%s', (photo['id'],))
        for position, photo in enumerate(retained):
            conn.execute('UPDATE part_draft_photos SET position=%s WHERE id=%s', (position, photo['id']))
        for position, data in enumerate(images, len(retained)):
            conn.execute('INSERT INTO part_draft_photos VALUES (%s,%s,%s,%s)', (uuid.uuid4(), draft['id'], position, data))
        return conn.execute('UPDATE part_drafts SET content=%s, revision=revision+1, updated_at=now() WHERE id=%s RETURNING *',
                            (Jsonb(content), draft['id'])).fetchone()

    @bp.post('/part-drafts')
    def create():
        validate_csrf()
        identifier = uuid.uuid4()
        with connect() as conn:
            original = None
            if request.form.get('request_id'):
                try:
                    request_id = uuid.UUID(request.form['request_id'])
                except ValueError:
                    abort(404)
                original = conn.execute('SELECT * FROM requests WHERE id=%s', (request_id,)).fetchone()
                if not original:
                    abort(404)
                if str(original['profile_revision']) != request.form.get('profile_revision'):
                    abort(409, description='The saved part changed. Reload before editing.')
            if conn.execute("SELECT count(*) AS n FROM part_drafts WHERE owner=%s AND updated_at > now()-interval '7 days' AND created_request_id IS NULL", (owner(),)).fetchone()['n'] >= 30:
                abort(429, description='Too many drafts. Resume an existing draft or wait for old drafts to expire.')
            content = dict(profile_revision=original['profile_revision'] if original else 0,
                           car_id=str(original['car_id'] or '') if original else '', vehicle=original['vehicle'] if original else request.form.get('vehicle', ''))
            draft = conn.execute('INSERT INTO part_drafts(id,owner,request_id,content) VALUES(%s,%s,%s,%s) RETURNING *',
                                 (identifier, owner(), original['id'] if original else None, Jsonb(content))).fetchone()
            if original:
                removed = request.form.getlist('remove_photos')
                rows = conn.execute('SELECT * FROM photos WHERE request_id=%s ORDER BY position', (original['id'],)).fetchall()
                for p in rows:
                    if str(p['id']) not in removed:
                        conn.execute('INSERT INTO part_draft_photos VALUES(%s,%s,%s,%s)', (uuid.uuid4(), identifier, p['position'], p['data']))
            draft = update_content(conn, draft)
            return jsonify(payload(conn, draft)), 201

    @bp.get('/part-drafts/<uuid:draft_id>')
    def get(draft_id):
        with connect() as conn:
            return jsonify(payload(conn, owned(conn, draft_id)))

    @bp.get('/part-drafts/<uuid:draft_id>/photos/<uuid:photo_id>')
    def photo(draft_id, photo_id):
        import io
        from flask import send_file
        with connect() as conn:
            owned(conn, draft_id)
            row = conn.execute('SELECT data FROM part_draft_photos WHERE draft_id=%s AND id=%s', (draft_id, photo_id)).fetchone()
            if not row:
                abort(404)
        response = send_file(io.BytesIO(row['data']), mimetype='image/jpeg')
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @bp.post('/part-drafts/<uuid:draft_id>/update')
    @bp.post('/part-drafts/<uuid:draft_id>/review')
    def update(draft_id):
        validate_csrf()
        with connect() as conn:
            draft = owned(conn, draft_id, True)
            revision(draft)
            return jsonify(payload(conn, update_content(conn, draft)))

    @bp.post('/part-drafts/<uuid:draft_id>/enrichments')
    def enrich(draft_id):
        validate_csrf()
        try:
            key = uuid.UUID(request.form.get('idempotency_key', ''))
        except ValueError:
            raise ValueError('Invalid request identifier.') from None
        with connect() as conn:
            draft = owned(conn, draft_id, True)
            previous = conn.execute('SELECT id FROM part_enrichments WHERE draft_id=%s AND idempotency_key=%s', (draft_id, key)).fetchone()
            if previous:
                return jsonify(id=str(previous['id'])), 202
            revision(draft)
            if conn.execute("SELECT id FROM part_enrichments WHERE draft_id=%s AND status IN ('queued','running')", (draft_id,)).fetchone():
                abort(409, description='AI is already filling this draft.')
            provider, _, model = request.form.get('model', '').partition(':')
            effort = request.form.get('reasoning_effort', '')
            if provider == 'codex':
                catalogue = cached_codex_models()
                if model and model not in catalogue:
                    raise ValueError('Refresh Codex models on the AI connections page.')
                if effort and effort not in catalogue.get(model, []):
                    raise ValueError('Choose a supported reasoning effort.')
            elif provider == 'openwebui':
                connection = conn.execute("SELECT * FROM ai_connections WHERE provider='openwebui'").fetchone()
                if not connection['api_key'] or model not in connection['models']:
                    raise ValueError('Configure Open WebUI and refresh its models.')
                effort = ''
            else:
                raise ValueError('Choose an AI connection and model.')
            if conn.execute("SELECT count(*) AS n FROM part_enrichments WHERE status IN ('queued','running')").fetchone()['n'] >= 20:
                abort(429, description='The AI queue is full. Try again later.')
            purpose = request.form.get('purpose', 'profile')
            if purpose not in {'profile', 'identifiers'}:
                raise ValueError('Choose a valid AI task.')
            run_id = uuid.uuid4()
            snapshot = dict(draft['content'], language_preferences=get_preferences(conn), purpose=purpose, include_photos=request.form.get('include_photos') == 'on')
            conn.execute('''INSERT INTO part_enrichments(id,draft_id,draft_revision,idempotency_key,provider,model,reasoning_effort,input,purpose)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (run_id, draft_id, draft['revision'], key, provider, model, effort, Jsonb(snapshot), purpose))
            if snapshot['include_photos']:
                conn.execute('INSERT INTO part_enrichment_photos SELECT %s,position,data FROM part_draft_photos WHERE draft_id=%s', (run_id, draft_id))
            return jsonify(id=str(run_id)), 202

    @bp.get('/part-drafts/<uuid:draft_id>/enrichments/<uuid:run_id>')
    def status(draft_id, run_id):
        with connect() as conn:
            owned(conn, draft_id)
            row = conn.execute('SELECT * FROM part_enrichments WHERE id=%s AND draft_id=%s', (run_id, draft_id)).fetchone()
            if not row:
                abort(404)
            return jsonify(id=str(row['id']), status=row['status'], output=row['output'], error=row['error'],
                           input=row['input'], draft_revision=row['draft_revision'], progress=progress_for(conn, row))

    @bp.post('/part-drafts/<uuid:draft_id>/enrichments/<uuid:run_id>/cancel')
    def cancel(draft_id, run_id):
        validate_csrf()
        with connect() as conn:
            owned(conn, draft_id, True)
            row = conn.execute("UPDATE part_enrichments SET status='cancelled',finished_at=now() WHERE id=%s AND draft_id=%s AND status IN ('queued','running','completed') RETURNING id", (run_id, draft_id)).fetchone()
            if not row:
                abort(409, description='This task has already ended.')
        return jsonify(status='cancelled', message='Results will not be applied. A running remote call may continue until its time limit.')

    @bp.post('/part-drafts/<uuid:draft_id>/commit')
    def commit(draft_id):
        validate_csrf()
        with connect() as conn:
            draft = owned(conn, draft_id, True)
            if draft['created_request_id']:
                return jsonify(url=url_for('detail', order_id=draft['created_request_id']))
            revision(draft)
            if conn.execute("SELECT id FROM part_enrichments WHERE draft_id=%s AND status IN ('queued','running')", (draft_id,)).fetchone():
                abort(409, description='Wait for AI to finish or cancel it before saving.')
            content = draft['content']
            profile = validate_profile(content['part_profile'])
            if content.get('review_state', {}).get('pending') or any(f['review_status'] == 'pending' for f in profile['facts']):
                raise ValueError('Review all AI suggestions before creating the part.')
            profile['facts'] = [f for f in profile['facts'] if f['review_status'] != 'rejected']
            car = resolve_car(conn, content['car_id'])
            order_id = draft['request_id'] or uuid.uuid4()
            if draft['request_id']:
                original = conn.execute('SELECT * FROM requests WHERE id=%s FOR UPDATE', (order_id,)).fetchone()
                if not original or original['profile_revision'] != content['profile_revision']:
                    abort(409, description='This part was edited elsewhere. Reload before saving.')
                conn.execute('UPDATE requests SET description=%s,vehicle=%s,car_id=%s,part_profile=%s,profile_revision=profile_revision+1 WHERE id=%s',
                             (content['description'], car['name'] if car else content['vehicle'], car['id'] if car else None, Jsonb(profile), order_id))
                conn.execute('DELETE FROM photos WHERE request_id=%s', (order_id,))
            else:
                conn.execute('INSERT INTO requests(id,description,vehicle,car_id,part_profile) VALUES(%s,%s,%s,%s,%s)',
                             (order_id, content['description'], car['name'] if car else content['vehicle'], car['id'] if car else None, Jsonb(profile)))
            conn.execute("INSERT INTO photos(id,request_id,content_type,data,position) SELECT gen_random_uuid(),%s,'image/jpeg',data,position FROM part_draft_photos WHERE draft_id=%s", (order_id, draft_id))
            conn.execute('UPDATE part_drafts SET created_request_id=%s,updated_at=now() WHERE id=%s', (order_id, draft_id))
            return jsonify(url=url_for('detail', order_id=order_id))

    return bp
