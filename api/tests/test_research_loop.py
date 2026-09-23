import json
import unittest
from unittest.mock import Mock, patch

from listings import listing_key, parse_research
from research_loop import run_research, compact_exclusions, EXCLUSION_PROMPT_CHARS


def answer(*urls, tokens=100, observed=True, notes=None, summary='Checked sources.'):
    return {'result': json.dumps({'summary_markdown': summary, 'listings': [
        {'url': url, 'title': 'Part'} for url in urls], 'research_notes': notes or {}}),
        'sources': list(urls), 'web_search_observed': observed, 'total_tokens': tokens}


class ResearchLoopTests(unittest.TestCase):
    def run_loop(self, responses, target=6, exclusions=None):
        run = Mock(side_effect=responses)
        refresh = exclusions if callable(exclusions) else lambda: exclusions or []
        result = run_research({'preferred_options': target, 'priority_websites': ['https://priority.com']},
                              run, refresh, Mock())
        return result, run

    def test_adaptive_rounds_stop_at_target_and_pass_compact_notes(self):
        result, run = self.run_loop([
            answer('https://seller.com/one', notes={'queries': ['reference A'], 'next_queries': ['reference B']}),
            answer('https://seller.com/one?utm_source=duplicate', 'https://seller.com/two')], target=2)
        self.assertEqual(len(result['listings']), 2)
        self.assertEqual(run.call_count, 2)
        second = run.call_args.args[0]
        self.assertEqual(second['preferred_options'], 1)
        self.assertEqual(second['research_round']['previous_research']['next_queries'], ['reference B'])
        self.assertEqual(second['excluded_listings'][0]['url'], 'https://seller.com/one')
        self.assertIn('open web', second['research_round']['strategy'])
        self.assertEqual(second['priority_websites'], ['https://priority.com'])

    def test_previous_blacklisted_and_in_round_duplicates_are_filtered(self):
        old = 'https://seller.com/old?id=1'
        result, run = self.run_loop([
            answer(old + '&utm_source=x', 'https://seller.com/new', 'https://seller.com/new#photo',
                   summary='[Old](https://seller.com/old?utm_source=x&id=1)\n\nFresh research.'),
            answer(old)], exclusions=[{'url': old, 'reason': 'Wrong side'}])
        self.assertEqual([item['url'] for item in result['listings']], ['https://seller.com/new'])
        self.assertNotIn('/old', result['result'])
        self.assertNotIn(old, result['sources'])
        self.assertEqual(run.call_count, 2)
        self.assertIn('No new listings', result['research_meta']['stop_reason'])

    def test_maximum_rounds_without_reported_usage(self):
        result, run = self.run_loop([answer(f'https://seller.com/{i}', tokens=None) for i in range(3)])
        self.assertEqual(run.call_count, 3)
        self.assertEqual(len(result['listings']), 3)
        self.assertFalse(result['research_meta']['usage_complete'])

    def test_token_budget_stops_before_another_round(self):
        result, run = self.run_loop([answer('https://seller.com/new', tokens=24000)])
        self.assertEqual(run.call_count, 1)
        self.assertIn('token budget', result['research_meta']['stop_reason'])

    def test_total_time_budget_stops_before_another_round(self):
        with patch('research_loop.time.monotonic', side_effect=[0, 0, 1801]):
            result, run = self.run_loop([answer('https://seller.com/new')])
        self.assertEqual(run.call_count, 1)
        self.assertIn('Time budget', result['research_meta']['stop_reason'])

    def test_openwebui_continues_after_total_time_budget(self):
        run = Mock(side_effect=[answer('https://seller.com/one'), answer('https://seller.com/two')])
        with patch('research_loop.time.monotonic', side_effect=[0, 1801, 7200]):
            result = run_research({'provider': 'openwebui', 'preferred_options': 2},
                                  run, lambda: [], Mock())
        self.assertEqual(run.call_count, 2)
        self.assertEqual(len(result['listings']), 2)
        self.assertIsNone(run.call_args.args[0]['round_timeout_seconds'])

    def test_no_web_evidence_does_not_trigger_more_calls(self):
        result, run = self.run_loop([answer(observed=False)])
        self.assertEqual(run.call_count, 1)
        self.assertFalse(result['web_search_observed'])

    def test_empty_first_round_still_tries_a_different_strategy(self):
        result, run = self.run_loop([answer(), answer('https://seller.com/new')], target=1)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(len(result['listings']), 1)

    def test_later_failure_retains_previous_results(self):
        with self.assertLogs(level='WARNING') as logs:
            result, run = self.run_loop([answer('https://seller.com/new'), ValueError('private upstream details')])
        self.assertIn('round 2 failed (ValueError)', logs.output[0])
        self.assertNotIn('private upstream details', logs.output[0])
        self.assertEqual(len(result['listings']), 1)
        self.assertIn('retained', result['research_meta']['stop_reason'])
        self.assertNotIn('private', json.dumps(result))

    def test_first_failure_is_reported(self):
        with self.assertRaisesRegex(ValueError, 'Failed'):
            self.run_loop([ValueError('Failed')])

    def test_exclusion_added_during_remote_call_is_enforced(self):
        entries = []
        def provider(job):
            entries.append({'url': 'https://seller.com/new', 'reason': 'Just removed'})
            return answer('https://seller.com/new')
        result = run_research({'preferred_options': 1}, provider, lambda: entries, Mock())
        self.assertEqual(result['listings'], [])
        self.assertEqual(result['sources'], [])

    def test_prompt_limit_does_not_limit_server_filter(self):
        excluded = [{'url': 'https://seller.com/' + str(i) + 'x' * 500, 'reason': 'Known'} for i in range(100)]
        compact = compact_exclusions(excluded)
        self.assertLess(sum(len(json.dumps(item, ensure_ascii=False)) for item in compact), EXCLUSION_PROMPT_CHARS + 1)
        self.assertLess(len(compact), len(excluded))
        result, _ = self.run_loop([answer(excluded[-1]['url']), answer()], exclusions=excluded)
        self.assertEqual(result['listings'], [])

    def test_fitment_contradictions_rejected_and_evidence_ranked(self):
        response = answer()
        response['result'] = json.dumps({'summary_markdown': 'Found', 'listings': [
            {'url': 'https://seller.com/unknown'},
            {'url': 'https://seller.com/wrong', 'fitment_status': 'incompatible'},
            {'url': 'https://seller.com/evidenced', 'fitment_status': 'supported',
             'compatibility': 'Reference matches', 'variant_checks': 'Phase and side match'}]})
        result, _ = self.run_loop([response], target=2)
        self.assertEqual([item['url'] for item in result['listings']],
                         ['https://seller.com/evidenced', 'https://seller.com/unknown'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
