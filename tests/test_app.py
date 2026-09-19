import io
import unittest
from unittest.mock import patch

from PIL import Image
from app import app, connect, normalize_photo


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        self.transaction = self.conn.transaction(force_rollback=True)
        self.transaction.__enter__()

        class SharedConnection:
            def __enter__(_self):
                return self.conn

            def __exit__(_self, *args):
                return False

        self.mock = patch('app.connect', return_value=SharedConnection())
        self.mock.start()
        self.client = app.test_client()
        self.client.get('/requests/new')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']

    def tearDown(self):
        self.mock.stop()
        self.transaction.__exit__(None, None, None)
        self.conn.close()

    def test_create_list_detail_and_photo(self):
        image = io.BytesIO()
        Image.new('RGB', (20, 20), 'blue').save(image, 'PNG')
        image.seek(0)
        response = self.client.post('/requests', data={
            'csrf': self.csrf, 'vehicle': 'Renault 19',
            'description': 'Left rear tail light <script>alert(1)</script>',
            'photos': (image, 'photo.png'),
        })
        self.assertEqual(response.status_code, 303)
        detail = self.client.get(response.location)
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b'&lt;script&gt;', detail.data)
        order_id = response.location.rsplit('/', 1)[-1]
        photo = self.conn.execute('SELECT id FROM photos WHERE request_id=%s', (order_id,)).fetchone()
        downloaded = self.client.get(f'/photos/{photo["id"]}')
        self.assertEqual(downloaded.mimetype, 'image/jpeg')
        Image.open(io.BytesIO(downloaded.data)).verify()
        self.assertIn(b'Renault 19', self.client.get('/').data)

    def test_description_only(self):
        response = self.client.post('/requests', data={'csrf': self.csrf, 'description': 'I need an alternator.'})
        self.assertEqual(response.status_code, 303)

    def test_car_profile_create_edit_and_link_request(self):
        data = {'csrf': self.csrf, 'name': 'My R19', 'make': 'Renault', 'model': '19 Chamade',
                'year': '1991', 'generation': 'Phase 1', 'rear_brakes': 'Drums', 'abs': 'No',
                'notes': '<script>not executable</script>'}
        response = self.client.post('/cars/new', data=data)
        self.assertEqual(response.status_code, 303)
        car_id = response.location.rsplit('/', 1)[-1]
        self.assertIn(b'&lt;script&gt;', self.client.get(response.location).data)
        self.assertIn(b'My R19', self.client.get('/cars').data)
        form = self.client.get('/requests/new?car_id=' + car_id).get_data(as_text=True)
        self.assertIn(f'value="{car_id}" selected', form)
        response = self.client.post('/requests', data={'csrf': self.csrf, 'car_id': car_id,
                                                     'description': 'Rear axle with drum brakes'})
        self.assertEqual(response.status_code, 303)
        order_id = response.location.rsplit('/', 1)[-1]
        order = self.conn.execute('SELECT * FROM requests WHERE id=%s', (order_id,)).fetchone()
        self.assertEqual(str(order['car_id']), car_id)
        self.assertEqual(order['vehicle'], 'My R19')
        self.assertIn(b'Technical specifications included', self.client.get(response.location).data)
        self.assertIn(b'Rear axle with drum brakes', self.client.get('/cars/' + car_id).data)
        self.client.post(f'/cars/{car_id}/edit', data=dict(data, name='Updated R19'))
        self.assertEqual(self.conn.execute('SELECT vehicle FROM requests WHERE id=%s', (order_id,)).fetchone()['vehicle'], 'Updated R19')
        self.assertEqual(self.client.post(f'/requests/{order_id}/edit', data={'csrf': self.csrf,
            'car_id': car_id, 'description': 'Updated rear axle description'}).status_code, 303)

    def test_car_validation(self):
        data = {'csrf': self.csrf, 'name': 'Test', 'make': 'Renault', 'model': '19'}
        for invalid in ({'csrf': 'bad'}, {'name': ''}, {'year': '9999'}, {'year': '00001991'}, {'abs': 'maybe'}, {'notes': 'x' * 3001}):
            self.assertEqual(self.client.post('/cars/new', data=dict(data, **invalid)).status_code, 400)
        self.assertEqual(self.client.post('/requests', data={'csrf': self.csrf, 'car_id': 'invalid',
            'description': 'Rear axle request'}).status_code, 400)
        self.assertEqual(self.client.get('/cars/00000000-0000-0000-0000-000000000000/edit').status_code, 404)

    def test_car_photo_upload_keep_replace_remove_and_invalid(self):
        def upload(color):
            image = io.BytesIO()
            Image.new('RGB', (40, 30), color).save(image, 'PNG')
            image.seek(0)
            return image, 'car.png'

        data = {'csrf': self.csrf, 'name': 'Photo car', 'make': 'Renault', 'model': '19'}
        response = self.client.post('/cars/new', data=dict(data, photo=upload('blue')))
        self.assertEqual(response.status_code, 303)
        car_url = response.location
        first = self.client.get(car_url + '/photo')
        self.assertEqual(first.mimetype, 'image/jpeg')
        Image.open(io.BytesIO(first.data)).verify()
        self.assertIn(b'Current photo', self.client.get(car_url + '/edit').data)
        self.assertIn((car_url + '/photo').encode(), self.client.get('/cars').data)
        self.client.post(car_url + '/edit', data=data)
        self.assertEqual(first.data, self.client.get(car_url + '/photo').data)
        invalid = self.client.post(car_url + '/edit', data=dict(data, name='Should not save',
                                  photo=(io.BytesIO(b'not-image'), 'bad.jpg'), remove_photo='1'))
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(first.data, self.client.get(car_url + '/photo').data)
        self.assertNotIn(b'Should not save', self.client.get(car_url).data)
        self.client.post(car_url + '/edit', data=dict(data, photo=upload('red'), remove_photo='1'))
        self.assertNotEqual(first.data, self.client.get(car_url + '/photo').data)
        self.client.post(car_url + '/edit', data=dict(data, remove_photo='1'))
        self.assertEqual(self.client.get(car_url + '/photo').status_code, 404)

    def test_car_photo_accepts_more_than_five_mb(self):
        def photo():
            stream = io.BytesIO()
            Image.new('RGB', (1500, 1500), 'blue').save(stream, 'PNG', compress_level=0)
            self.assertGreater(stream.tell(), 5 * 1024 * 1024)
            stream.seek(0)
            return stream, 'big.png'

        data = {'csrf': self.csrf, 'name': 'Big photo', 'make': 'Renault', 'model': '19'}
        response = self.client.post('/cars/new', data=dict(data, photos=photo()))
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get(response.location + '/photo').mimetype, 'image/jpeg')
        self.assertEqual(self.client.post(response.location + '/edit',
            data=dict(data, photos=photo())).status_code, 303)
        car_id = response.location.rsplit('/', 1)[-1]
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM car_photos WHERE car_id=%s',
            (car_id,)).fetchone()['n'], 2)

    def test_phone_photo_orientation_and_proportions(self):
        for orientation in range(1, 9):
            with self.subTest(orientation=orientation):
                source = io.BytesIO()
                exif = Image.Exif()
                exif[274] = orientation
                Image.new('RGB', (120, 80), 'blue').save(source, 'JPEG', exif=exif)
                source.seek(0)
                with Image.open(io.BytesIO(normalize_photo(source))) as result:
                    self.assertEqual(result.size, (80, 120) if orientation >= 5 else (120, 80))
                    self.assertIsNone(result.getexif().get(274))
        for size, expected in (((3000, 1500), (2000, 1000)), ((1500, 3000), (1000, 2000))):
            source = io.BytesIO()
            Image.new('RGB', size, 'blue').save(source, 'JPEG')
            source.seek(0)
            with Image.open(io.BytesIO(normalize_photo(source))) as result:
                self.assertEqual(result.size, expected)

    def test_car_gallery_upload_and_homepage(self):
        def photo(color):
            stream = io.BytesIO()
            Image.new('RGB', (30, 50), color).save(stream, 'PNG')
            stream.seek(0)
            return stream, 'car.png'
        data = {'csrf': self.csrf, 'name': 'Gallery car', 'make': 'Renault', 'model': '19'}
        response = self.client.post('/cars/new', data=dict(data, photos=[photo('red')] + [photo('blue') for _ in range(6)]))
        self.assertEqual(response.status_code, 303)
        car_id = response.location.rsplit('/', 1)[-1]
        photos = self.conn.execute('SELECT id FROM car_photos WHERE car_id=%s ORDER BY position', (car_id,)).fetchall()
        self.assertEqual(len(photos), 7)
        page = self.client.get('/').get_data(as_text=True)
        self.assertIn('Gallery car', page)
        self.assertIn('Pause slideshow', page)
        for row in photos:
            url = f'/cars/{car_id}/photos/{row["id"]}'
            self.assertIn(url, page)
            self.assertEqual(self.client.get(url).mimetype, 'image/jpeg')
        self.assertEqual(self.client.post(response.location + '/edit', data=dict(data,
            photos=[photo('red') for _ in range(5)])).status_code, 303)
        self.assertEqual(self.client.post(response.location + '/edit', data=dict(data,
            remove_photos=['00000000-0000-0000-0000-000000000000'])).status_code, 400)
        self.assertEqual(self.client.post(response.location + '/edit', data=dict(data,
            remove_photos=[str(photos[0]['id'])], photos=[photo('green')])).status_code, 303)
        current = self.conn.execute('SELECT id, position FROM car_photos WHERE car_id=%s ORDER BY position', (car_id,)).fetchall()
        self.assertEqual(len(current), 12)
        self.assertEqual(current[0]['id'], photos[1]['id'])
        self.assertEqual([row['position'] for row in current], list(range(12)))

    def test_validation(self):
        self.assertEqual(self.client.post('/requests', data={'description': 'Missing CSRF token'}).status_code, 400)
        self.assertEqual(self.client.post('/requests', data={'csrf': self.csrf, 'description': 'short'}).status_code, 400)
        before = self.conn.execute('SELECT count(*) AS n FROM requests').fetchone()['n']
        response = self.client.post('/requests', data={'csrf': self.csrf, 'description': 'A sample car part', 'photos': (io.BytesIO(b'not an image'), 'fake.jpg')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, self.conn.execute('SELECT count(*) AS n FROM requests').fetchone()['n'])
        photos = [(io.BytesIO(b'x'), f'{i}.jpg') for i in range(7)]
        self.assertEqual(self.client.post('/requests', data={'csrf': self.csrf, 'description': 'A sample car part', 'photos': photos}).status_code, 400)

    def test_health_and_missing(self):
        self.assertEqual(self.client.get('/health').json, {'status': 'ok'})
        self.assertEqual(self.client.get('/requests/00000000-0000-0000-0000-000000000000').status_code, 404)

    def create_with_photos(self, count=1):
        uploads = []
        for i in range(count):
            image = io.BytesIO()
            Image.new('RGB', (20, 20), 'blue').save(image, 'PNG')
            image.seek(0)
            uploads.append((image, f'{i}.png'))
        response = self.client.post('/requests', data={
            'csrf': self.csrf, 'description': 'Original part description',
            'vehicle': 'Renault 19', 'photos': uploads,
        })
        self.assertEqual(response.status_code, 303)
        return response.location.rsplit('/', 1)[-1]

    def test_edit_text_preserves_photos_and_identity(self):
        order_id = self.create_with_photos()
        original = self.conn.execute('SELECT * FROM requests WHERE id=%s', (order_id,)).fetchone()
        photos = self.conn.execute('SELECT * FROM photos WHERE request_id=%s', (order_id,)).fetchall()
        url = f'/requests/{order_id}/edit'
        form = self.client.get(url)
        self.assertEqual(form.status_code, 200)
        self.assertIn(b'Original part description', form.data)
        self.assertEqual(self.client.post(url, data={
            'csrf': self.csrf, 'description': 'New part description', 'vehicle': 'Renault Clio',
        }).status_code, 303)
        updated = self.conn.execute('SELECT * FROM requests WHERE id=%s', (order_id,)).fetchone()
        self.assertEqual(updated['created_at'], original['created_at'])
        self.assertEqual(updated['vehicle'], 'Renault Clio')
        self.assertEqual(updated['description'], 'New part description')
        self.assertEqual(photos, self.conn.execute('SELECT * FROM photos WHERE request_id=%s', (order_id,)).fetchall())

    def test_edit_photos_and_validation_are_atomic(self):
        order_id = self.create_with_photos(6)
        url = f'/requests/{order_id}/edit'
        photos = self.conn.execute('SELECT id FROM photos WHERE request_id=%s ORDER BY position', (order_id,)).fetchall()
        removed = str(photos[0]['id'])
        base = {'csrf': self.csrf, 'description': 'Updated part description'}
        # Retained photos count towards the limit; invalid submissions change nothing.
        response = self.client.post(url, data={**base, 'photos': (io.BytesIO(b'invalid'), 'bad.jpg')})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(url, data={**base, 'remove_photos': removed, 'photos': (io.BytesIO(b'invalid'), 'bad.jpg')})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'checked', response.data)
        self.assertEqual(self.conn.execute('SELECT description FROM requests WHERE id=%s', (order_id,)).fetchone()['description'], 'Original part description')
        self.assertEqual(len(self.conn.execute('SELECT id FROM photos WHERE request_id=%s', (order_id,)).fetchall()), 6)
        image = io.BytesIO()
        Image.new('RGB', (10, 10), 'red').save(image, 'PNG')
        image.seek(0)
        self.assertEqual(self.client.post(url, data={**base, 'remove_photos': removed, 'photos': (image, 'new.png')}).status_code, 303)
        updated = self.conn.execute('SELECT id, position FROM photos WHERE request_id=%s ORDER BY position', (order_id,)).fetchall()
        self.assertEqual([p['position'] for p in updated], list(range(6)))
        self.assertNotIn(removed, [str(p['id']) for p in updated])
        self.assertEqual(self.client.post(url, data={**base, 'remove_photos': [str(p['id']) for p in updated]}).status_code, 303)
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM photos WHERE request_id=%s', (order_id,)).fetchone()['n'], 0)

    def test_edit_rejects_csrf_foreign_photo_and_missing_order(self):
        order_id = self.create_with_photos()
        other_id = self.create_with_photos()
        foreign = self.conn.execute('SELECT id FROM photos WHERE request_id=%s', (other_id,)).fetchone()['id']
        url = f'/requests/{order_id}/edit'
        self.assertEqual(self.client.post(url, data={'description': 'Updated description'}).status_code, 400)
        self.assertEqual(self.client.post(url, data={'csrf': self.csrf, 'description': 'Updated description', 'remove_photos': str(foreign)}).status_code, 400)
        self.assertEqual(self.client.get(f'/photos/{foreign}').status_code, 200)
        missing = '/requests/00000000-0000-0000-0000-000000000000/edit'
        self.assertEqual(self.client.get(missing).status_code, 404)
        self.assertEqual(self.client.post(missing, data={'csrf': self.csrf}).status_code, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
