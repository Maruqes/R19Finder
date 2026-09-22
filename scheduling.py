"""Weekly Lisbon schedules and shared research queue insertion."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import uuid

from psycopg.types.json import Jsonb
from language_settings import get_preferences
from listings import excluded_for_request

LISBON = ZoneInfo('Europe/Lisbon')
DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')


def next_occurrence(weekday, local_time, after=None):
    after = after or datetime.now(timezone.utc)
    local = after.astimezone(LISBON)
    for offset in range(8):
        date = local.date() + timedelta(days=offset)
        if date.weekday() != weekday:
            continue
        candidate = datetime.combine(date, local_time, LISBON).astimezone(timezone.utc)
        # Spring clock gaps move forward; autumn repeats run once (first occurrence).
        if candidate > after:
            return candidate
    raise ValueError('Unable to calculate next schedule occurrence.')


def enqueue_search(conn, order, settings, schedule_id=None, discord_notify=False):
    search_id = uuid.uuid4()
    car = conn.execute('SELECT * FROM cars WHERE id=%s', (order['car_id'],)).fetchone() if order.get('car_id') else None
    car_profile = dict(car['specs'], name=car['name']) if car else {}
    excluded = excluded_for_request(conn, order['id'])
    conn.execute('''INSERT INTO searches (id, request_id, provider, model, instructions, vehicle, description,
        preferred_price, pickup_areas, shipping_areas, reasoning_effort, preferred_options, priority_websites, schedule_id, car_profile, excluded_listings, discord_notify, part_profile, language_preferences)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
        (search_id, order['id'], settings['provider'], settings['model'], settings['instructions'],
         car['name'] if car else order['vehicle'], order['description'], settings['preferred_price'], settings['pickup_areas'],
         settings['shipping_areas'], settings['reasoning_effort'], settings['preferred_options'],
         Jsonb(settings['priority_websites']), schedule_id, Jsonb(car_profile), Jsonb(excluded), bool(schedule_id and discord_notify), Jsonb(order.get('part_profile', {})), Jsonb(get_preferences(conn))))
    conn.execute('''INSERT INTO search_photos (search_id, position, data)
        SELECT %s, position, data FROM photos WHERE request_id=%s''', (search_id, order['id']))
    return search_id


def dispatch_due(conn, now=None):
    now = now or datetime.now(timezone.utc)
    # Serialize scheduler instances; request locks also coordinate manual searches.
    if not conn.execute('SELECT pg_try_advisory_xact_lock(190020) AS locked').fetchone()['locked']:
        return 0
    schedules = conn.execute('''SELECT * FROM schedules WHERE enabled AND next_run <= %s
        ORDER BY next_run, id FOR UPDATE SKIP LOCKED''', (now,)).fetchall()
    queued = 0
    for schedule in schedules:
        order = conn.execute('SELECT * FROM requests WHERE id=%s FOR UPDATE', (schedule['request_id'],)).fetchone()
        active = conn.execute("SELECT id FROM searches WHERE request_id=%s AND status IN ('queued', 'running')",
                              (schedule['request_id'],)).fetchone()
        if active:
            # Keep this occurrence due and retry after the active search completes.
            conn.execute("UPDATE schedules SET last_message='Waiting for the active search to finish.' WHERE id=%s", (schedule['id'],))
            continue
        enqueue_search(conn, order, schedule['settings'], schedule['id'], schedule['discord_notify'])
        conn.execute('''UPDATE schedules SET last_run=%s, last_message='Search queued.', next_run=%s WHERE id=%s''',
                     (now, next_occurrence(schedule['weekday'], schedule['local_time'], now), schedule['id']))
        queued += 1
    return queued
