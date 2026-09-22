"""Durable single-worker queue for optional part profile enrichment."""
import json
import logging
import time
import threading
from worker_locks import ENRICHMENT_WORKER, AI_GENERATION

from psycopg.types.json import Jsonb
from worker import connect
from search import run_codex, run_openwebui
from part_enrichment import run_openwebui_profile
from part_profile import enrichment_prompt, ENRICHMENT_SCHEMA, parse_suggestions


def process_job(job):
    def progress(stage):
        with connect() as conn:
            conn.execute("UPDATE part_enrichments SET stage=%s,progress_at=now() WHERE id=%s AND status='running'", (stage, job['id']))
        logging.info('Enrichment %s: %s', job['id'], stage)
    def provider_progress(stage):
        progress('researching_identifiers' if stage == 'generating' and job.get('purpose') == 'identifiers' else stage)

    def save_remote(url):
        with connect() as conn:
            conn.execute('UPDATE part_enrichments SET remote_url=%s WHERE id=%s', (url, job['id']))

    def is_cancelled():
        with connect() as conn:
            row = conn.execute('SELECT status FROM part_enrichments WHERE id=%s', (job['id'],)).fetchone()
            return not row or row['status'] != 'running'

    try:
        progress('preparing')
        with connect() as conn:
            photos = conn.execute('SELECT data FROM part_enrichment_photos WHERE run_id=%s ORDER BY position', (job['id'],)).fetchall()
            connection = conn.execute('SELECT * FROM ai_connections WHERE provider=%s', (job['provider'],)).fetchone()
        transport = dict(job, vehicle=job['input']['vehicle'], round_timeout_seconds=300)
        text = json.dumps(job['input'], ensure_ascii=False)
        progress('connecting')
        if job['provider'] == 'codex':
            result = run_codex(transport, photos, system_prompt=enrichment_prompt(job['input']), input_text=text, output_schema=ENRICHMENT_SCHEMA, is_cancelled=is_cancelled, on_progress=provider_progress)
        elif job.get('purpose') == 'identifiers':
            progress('researching_identifiers')
            result = run_openwebui(transport, photos, connection, save_remote,
                system_prompt=enrichment_prompt(job['input']) + '\nJSON schema:\n' + json.dumps(ENRICHMENT_SCHEMA),
                input_text=text, require_web=True, is_cancelled=is_cancelled)
        else:
            result = run_openwebui_profile(job, photos, connection, is_cancelled, on_progress=provider_progress)
        progress('validating')
        output = parse_suggestions(result['result'], job['id'], observed_sources=result.get('sources', []),
                                   web_observed=result.get('web_search_observed', False), purpose=job.get('purpose', 'profile'),
                                   response_language=job['input'].get('language_preferences', {}).get('response_language', 'en'))
        with connect() as conn:
            conn.execute("UPDATE part_enrichments SET status='completed',stage='completed',progress_at=now(),output=%s,finished_at=now() WHERE id=%s AND status='running'", (Jsonb(output), job['id']))
    except Exception as error:
        logging.error('Part enrichment %s failed (%s)', job['id'], type(error).__name__)
        message = str(error) if isinstance(error, ValueError) else 'AI fill failed. Check the connection and retry. Your draft is safe.'
        with connect() as conn:
            conn.execute("UPDATE part_enrichments SET status='failed',stage='failed',progress_at=now(),error=%s,finished_at=now() WHERE id=%s AND status='running'", (message, job['id']))


def heartbeat_loop():
    while True:
        try:
            with connect() as conn:
                conn.execute("INSERT INTO worker_heartbeats(name,seen_at) VALUES('enrichment',now()) ON CONFLICT(name) DO UPDATE SET seen_at=now()")
        except Exception as error:
            logging.error('Enrichment heartbeat failed (%s)', type(error).__name__)
        time.sleep(5)


def main():
    logging.basicConfig(level=logging.INFO)
    with connect() as lock:
        lock.autocommit = True
        if not lock.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (ENRICHMENT_WORKER,)).fetchone()['acquired']:
            raise SystemExit('Another enrichment worker is running.')
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        logging.info('Enrichment worker online')
        with connect() as conn:
            conn.execute("UPDATE part_enrichments SET status='failed',finished_at=now(),error='Worker restarted. Check your provider before retrying.' WHERE status='running'")
        while True:
            lock.execute('SELECT 1')
            # Shared session lock serializes generation with the research worker.
            if not lock.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (AI_GENERATION,)).fetchone()['acquired']:
                time.sleep(2)
                continue
            try:
                with connect() as conn:
                    conn.execute("DELETE FROM part_drafts WHERE updated_at < now()-interval '7 days' AND NOT EXISTS (SELECT 1 FROM part_enrichments WHERE draft_id=part_drafts.id AND status='running')")
                    job = conn.execute("SELECT * FROM part_enrichments WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
                    if job:
                        conn.execute("UPDATE part_enrichments SET status='running',stage='preparing',progress_at=now(),started_at=now() WHERE id=%s", (job['id'],))
                if job:
                    process_job(job)
            finally:
                lock.execute('SELECT pg_advisory_unlock(%s)', (AI_GENERATION,))
            if not job:
                time.sleep(2)


if __name__ == '__main__':
    main()
