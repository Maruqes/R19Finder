"""Single background worker using PostgreSQL as a durable research queue."""
import logging
import os
import time

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from search import run_codex, run_openwebui
from listings import excluded_for_request, exclusion_keys, listing_key, remove_excluded_links
from research_loop import run_research


def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, connect_timeout=5)


def claim_job():
    with connect() as conn:
        job = conn.execute("SELECT * FROM searches WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if job:
            conn.execute("UPDATE searches SET status='running', started_at=now() WHERE id=%s", (job['id'],))
        return job


def process_job(job):
    def save_remote(url):
        with connect() as conn:
            conn.execute('UPDATE searches SET remote_url=%s WHERE id=%s', (url, job['id']))

    def refresh_exclusions():
        with connect() as conn:
            current = excluded_for_request(conn, job['request_id'])
        # Keep the original snapshot as well as edits made while queued/running.
        combined = {listing_key(item['url']): item for item in job.get('excluded_listings', [])}
        combined.update({listing_key(item['url']): item for item in current})
        return list(combined.values())

    def save_progress(meta):
        with connect() as conn:
            conn.execute('UPDATE searches SET research_meta=%s WHERE id=%s', (Jsonb(meta), job['id']))

    try:
        with connect() as conn:
            photos = conn.execute('SELECT data FROM search_photos WHERE search_id=%s ORDER BY position', (job['id'],)).fetchall()
            connection = conn.execute('SELECT * FROM ai_connections WHERE provider=%s', (job['provider'],)).fetchone()
        def run_round(round_job):
            if job['provider'] == 'codex':
                return run_codex(round_job, photos)
            return run_openwebui(round_job, photos, connection, save_remote)

        result = run_research(job, run_round, refresh_exclusions, save_progress)
        with connect() as conn:
            # Coordinate this final check with removals and newly queued searches.
            conn.execute('SELECT id FROM requests WHERE id=%s FOR UPDATE', (job['request_id'],))
            blocked = exclusion_keys(excluded_for_request(conn, job['request_id']))
            listings = [item for item in result['listings'] if listing_key(item['url']) not in blocked]
            summary = remove_excluded_links(result['result'], blocked)
            sources = [url for url in result['sources'] if listing_key(url) not in blocked]
            result['research_meta']['new_listings'] = len(listings)
            conn.execute("""UPDATE searches SET status='completed', result=%s, sources=%s,
                web_search_observed=%s, listings=%s, research_meta=%s, finished_at=now() WHERE id=%s""",
                (summary, Jsonb(sources), result['web_search_observed'], Jsonb(listings), Jsonb(result['research_meta']), job['id']))
            if job.get('discord_notify') and job.get('schedule_id') and listings:
                # Commit the delivery queue entry with the results; Discord failures cannot undo research.
                conn.execute('INSERT INTO discord_notifications (search_id) VALUES (%s) ON CONFLICT DO NOTHING',
                             (job['id'],))
    except Exception as error:
        if isinstance(error, ValueError):
            message = str(error)
        elif isinstance(error, httpx.TimeoutException):
            message = 'The provider timed out. Check the provider conversation before retrying.'
        elif isinstance(error, httpx.RequestError):
            message = 'Unable to reach the AI provider. Check its connection settings.'
        else:
            message = 'Research failed unexpectedly. Check the worker service and try again.'
        # Do not log exception bodies or provider payloads: they may contain credentials.
        logging.error('Research %s failed (%s)', job['id'], type(error).__name__)
        with connect() as conn:
            conn.execute("UPDATE searches SET status='failed', error=%s, finished_at=now() WHERE id=%s", (message, job['id']))


def main():
    logging.basicConfig(level=logging.INFO)
    # Keep a session lock: only one worker may recover and process this queue.
    with connect() as lock:
        lock.autocommit = True
        if not lock.execute('SELECT pg_try_advisory_lock(190019) AS acquired').fetchone()['acquired']:
            raise SystemExit('Another research worker is already running.')
        with connect() as conn:
            conn.execute("""UPDATE searches SET status='failed', finished_at=now(),
                error='The worker restarted during this search. Check the provider conversation before starting another search.'
                WHERE status='running'""")
        while True:
            lock.execute('SELECT 1')
            job = claim_job()
            if job:
                process_job(job)
            else:
                time.sleep(2)


if __name__ == '__main__':
    main()
