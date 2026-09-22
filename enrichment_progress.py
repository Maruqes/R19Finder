"""Safe, observable enrichment phases; no provider reasoning or private payloads."""
from datetime import datetime, timezone

STAGES = {
    'preparing': 'Preparing the part details and photos.',
    'connecting': 'Checking the AI connection and model.',
    'generating': 'The AI is generating suggestions. Waiting for its response.',
    'researching_identifiers': 'Researching exact identifiers and checking the part variant against sources.',
    'validating': 'Checking the suggested fields before showing them.',
}


def progress_for(conn, job):
    now = datetime.now(timezone.utc)
    age = lambda value: max(0, int((now - value).total_seconds())) if value else 0
    heartbeat = conn.execute("SELECT seen_at FROM worker_heartbeats WHERE name='enrichment'").fetchone()
    seen = heartbeat['seen_at'] if heartbeat else None
    online = bool(seen and age(seen) < 25)
    ahead = 0
    reason = job['status']
    if job['status'] == 'queued':
        ahead = conn.execute("""SELECT count(*) AS n FROM part_enrichments
            WHERE (status='running' OR (status='queued' AND (created_at,id)<(%s,%s))) AND id<>%s""",
            (job['created_at'], job['id'], job['id'])).fetchone()['n']
        research = conn.execute("SELECT count(*) AS n FROM searches WHERE status='running'").fetchone()['n']
        if not online:
            reason, message = 'worker_unavailable', 'The AI worker is not responding. Your request is saved and will start when the service returns.'
        elif research:
            reason, message = 'research_busy', 'Waiting for an active parts search to finish. Both tasks share the AI connection.'
        elif ahead:
            reason, message = 'queue_busy', f'Waiting behind {ahead} other AI fill task(s).'
        elif age(job['created_at']) > 20:
            reason, message = 'dispatch_delayed', 'The worker is online but has not picked up this request yet. Dispatch is delayed.'
        else:
            reason, message = 'ready', 'The worker is online. Your request is next to start.'
    elif job['status'] == 'running':
        if not online:
            reason, message = 'worker_unavailable', 'The worker stopped reporting while processing. Your draft is safe; do not submit another AI fill.'
        else:
            message = STAGES.get(job.get('stage'), 'The AI is processing your request.')
    else:
        message = {'completed': 'Suggestions are ready for review.', 'failed': job.get('error') or 'AI fill failed.',
                   'cancelled': 'AI fill was cancelled.'}.get(job['status'], '')
    return dict(reason=reason, message=message, worker_online=online,
                worker_last_seen=seen.isoformat() if seen else None,
                queue_position=ahead + 1 if job['status'] == 'queued' else None,
                elapsed_seconds=age(job['created_at']), running_seconds=age(job.get('started_at')),
                stage=job.get('stage', 'queued'), provider=job['provider'], model=job['model'],
                checked_at=now.isoformat(), timeout_seconds=300)
