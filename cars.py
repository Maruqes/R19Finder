"""Reusable vehicle profiles for parts compatibility research."""
from datetime import date
import io
import uuid

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, send_file
from psycopg.types.json import Jsonb

CAR_FIELDS = (
    ('make', 'Make', 'Renault'), ('model', 'Model', '19 Chamade'),
    ('year', 'Year', '1991'), ('generation', 'Generation / phase', 'Phase 1'),
    ('body_style', 'Body style', '4-door saloon'), ('trim', 'Trim / version', 'GTS'),
    ('engine', 'Engine / displacement', '1.4 petrol, 1390 cc'),
    ('engine_code', 'Engine code', 'Enter the code if known'),
    ('power', 'Power (include unit)', '80 hp / 59 kW'),
    ('fuel', 'Fuel', 'Petrol'), ('transmission', 'Transmission', '5-speed manual'),
    ('drive', 'Driven wheels', 'Front-wheel drive'),
    ('abs', 'ABS', ''), ('front_brakes', 'Front brakes', 'Discs'),
    ('rear_brakes', 'Rear brakes', 'Drums'), ('steering', 'Steering position', 'Left-hand drive'),
)

CAR_QUERY = '''SELECT c.*, ARRAY(SELECT p.id FROM car_photos p WHERE p.car_id=c.id
    ORDER BY p.position, p.id) AS photo_ids FROM cars c'''


def resolve_car(conn, value):
    if not value:
        return None
    try:
        car_id = uuid.UUID(value)
    except ValueError:
        raise ValueError('Choose a valid car profile.') from None
    car = conn.execute('SELECT * FROM cars WHERE id=%s', (car_id,)).fetchone()
    if not car:
        raise ValueError('This car profile no longer exists. Choose another car.')
    return car


def create_cars_blueprint(connect, validate_csrf, normalize_photo):
    bp = Blueprint('cars', __name__)
    car_query = CAR_QUERY

    @bp.get('/cars')
    def index():
        with connect() as conn:
            cars = conn.execute(car_query + ' ORDER BY name, id').fetchall()
        return render_template('cars.html', cars=cars)

    @bp.route('/cars/new', methods=['GET', 'POST'])
    @bp.route('/cars/<uuid:car_id>/edit', methods=['GET', 'POST'])
    def edit(car_id=None):
        if request.method == 'POST':
            validate_csrf()
        with connect() as conn:
            car = conn.execute(car_query + ' WHERE c.id=%s FOR UPDATE OF c', (car_id,)).fetchone() if car_id else None
            if car_id and not car:
                abort(404)
            values = dict(car['specs'], name=car['name']) if car else {}
            error = None
            if request.method == 'POST':
                values = {key: request.form.get(key, '').strip()
                          for key in ('name', 'notes', *(field[0] for field in CAR_FIELDS))}
                if not all(values[key] for key in ('name', 'make', 'model')):
                    error = 'Enter a profile name, make and model.'
                elif any(len(value) > (3000 if key == 'notes' else 120) for key, value in values.items()):
                    error = 'Use up to 120 characters per field and 3000 for notes.'
                elif values['year'] and (len(values['year']) != 4 or not values['year'].isascii() or not values['year'].isdigit()
                        or not 1900 <= int(values['year']) <= date.today().year + 1):
                    error = 'Enter a valid four-digit vehicle year.'
                elif values['abs'] not in ('', 'Yes', 'No'):
                    error = 'Choose Yes, No or Unknown for ABS.'
                photo_data = []
                existing = car['photo_ids'] if car else []
                removed = set(request.form.getlist('remove_photos'))
                if request.form.get('remove_photo') == '1':
                    removed = {str(photo_id) for photo_id in existing}
                remaining = [photo_id for photo_id in existing if str(photo_id) not in removed]
                if not error:
                    try:
                        uploads = [upload for upload in request.files.getlist('photos') + request.files.getlist('photo') if upload.filename]
                        if not removed.issubset({str(photo_id) for photo_id in existing}):
                            raise ValueError('One of the photos does not belong to this car. Refresh the page.')
                        if len(remaining) + len(uploads) > 6:
                            raise ValueError('A car can have up to 6 photos. Remove some before adding more.')
                        photo_data = [normalize_photo(upload) for upload in uploads]
                    except ValueError as invalid_photo:
                        error = str(invalid_photo)
                if not error:
                    specs = {key: value for key, value in values.items() if key != 'name'}
                    if car_id:
                        conn.execute('UPDATE cars SET name=%s, specs=%s WHERE id=%s', (values['name'], Jsonb(specs), car_id))
                        conn.execute('UPDATE requests SET vehicle=%s WHERE car_id=%s', (values['name'], car_id))
                    else:
                        car_id = uuid.uuid4()
                        conn.execute('INSERT INTO cars (id, name, specs) VALUES (%s, %s, %s)', (car_id, values['name'], Jsonb(specs)))
                    for photo_id in removed:
                        conn.execute('DELETE FROM car_photos WHERE car_id=%s AND id=%s', (car_id, uuid.UUID(photo_id)))
                    for position, photo_id in enumerate(remaining):
                        conn.execute('UPDATE car_photos SET position=%s WHERE id=%s', (position, photo_id))
                    for position, data in enumerate(photo_data, start=len(remaining)):
                        conn.execute('INSERT INTO car_photos (car_id, data, position) VALUES (%s, %s, %s)', (car_id, data, position))
                    flash('Car profile saved. Future searches use the updated specifications.')
                    return redirect(url_for('cars.detail', car_id=car_id), code=303)
        return render_template('car_form.html', car=car, values=values, fields=CAR_FIELDS, error=error), 400 if error else 200

    @bp.get('/cars/<uuid:car_id>')
    def detail(car_id):
        with connect() as conn:
            car = conn.execute(car_query + ' WHERE c.id=%s', (car_id,)).fetchone()
            if not car:
                abort(404)
            orders = conn.execute('SELECT * FROM requests WHERE car_id=%s ORDER BY created_at DESC', (car_id,)).fetchall()
        return render_template('car_detail.html', car=car, fields=CAR_FIELDS, orders=orders)

    @bp.get('/cars/<uuid:car_id>/photo')
    @bp.get('/cars/<uuid:car_id>/photos/<uuid:photo_id>')
    def photo(car_id, photo_id=None):
        with connect() as conn:
            row = conn.execute('''SELECT data FROM car_photos WHERE car_id=%s
                AND (%s::uuid IS NULL OR id=%s) ORDER BY position, id LIMIT 1''', (car_id, photo_id, photo_id)).fetchone()
        if not row:
            abort(404)
        response = send_file(io.BytesIO(row['data']), mimetype='image/jpeg', max_age=0)
        response.headers['Cache-Control'] = 'no-store'
        return response

    return bp
