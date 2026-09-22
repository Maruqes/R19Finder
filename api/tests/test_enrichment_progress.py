import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import uuid

from enrichment_progress import progress_for
import worker_locks


class ProgressTests(unittest.TestCase):
    def job(self, **values):
        return dict(id=uuid.uuid4(), status='queued', created_at=datetime.now(timezone.utc)-timedelta(seconds=50),
                    started_at=None, provider='codex', model='test-model', **values)

    def connection(self, *rows):
        conn = Mock()
        conn.execute.side_effect = [Mock(fetchone=Mock(return_value=row)) for row in rows]
        return conn

    def test_discord_and_ai_locks_are_distinct(self):
        ids = [getattr(worker_locks, name) for name in ('RESEARCH_WORKER','SCHEDULER','DISCORD_SETTINGS','DISCORD_WORKER','ENRICHMENT_WORKER','AI_GENERATION')]
        self.assertEqual(len(ids), len(set(ids)))

    def test_offline_worker_is_not_reported_as_normal_queue(self):
        result = progress_for(self.connection(None, {'n': 0}, {'n': 0}), self.job())
        self.assertEqual(result['reason'], 'worker_unavailable')
        self.assertFalse(result['worker_online'])

    def test_reports_shared_connection_blocker(self):
        result = progress_for(self.connection({'seen_at': datetime.now(timezone.utc)}, {'n': 0}, {'n': 1}), self.job())
        self.assertEqual(result['reason'], 'research_busy')
        self.assertEqual(result['queue_position'], 1)

    def test_reports_queue_position_and_elapsed_time(self):
        result = progress_for(self.connection({'seen_at': datetime.now(timezone.utc)}, {'n': 2}, {'n': 0}), self.job())
        self.assertEqual(result['queue_position'], 3)
        self.assertEqual(result['reason'], 'queue_busy')
        self.assertGreaterEqual(result['elapsed_seconds'], 50)

    def test_online_but_delayed_dispatch_is_visible(self):
        result = progress_for(self.connection({'seen_at': datetime.now(timezone.utc)}, {'n': 0}, {'n': 0}), self.job())
        self.assertEqual(result['reason'], 'dispatch_delayed')

    def test_running_stage_and_stale_heartbeat(self):
        job = self.job(); job.update(status='running', stage='generating', started_at=datetime.now(timezone.utc)-timedelta(seconds=10))
        result = progress_for(self.connection({'seen_at': datetime.now(timezone.utc)}), job)
        self.assertIn('generating', result['message'])
        result = progress_for(self.connection({'seen_at': datetime.now(timezone.utc)-timedelta(seconds=40)}), job)
        self.assertEqual(result['reason'], 'worker_unavailable')
