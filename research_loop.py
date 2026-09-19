"""Bounded, provider-independent discovery with server-side exclusion enforcement."""
import json
import time

from listings import exclusion_keys, listing_key, parse_research, public_url, remove_excluded_links

MAX_ROUNDS = 3
TOKEN_BUDGET = 24000
TOTAL_SECONDS = 1800
ROUND_SECONDS = 600
MAX_OUTPUT_TOKENS = 5000
EXCLUSION_PROMPT_CHARS = 16000


def compact_exclusions(entries):
    result, size = [], 0
    for entry in entries:
        item = {'url': entry['url'], 'reason': entry.get('reason', '')[:200]}
        length = len(json.dumps(item, ensure_ascii=False))
        if size + length > EXCLUSION_PROMPT_CHARS:
            continue
        result.append(item)
        size += length
    return result


def research_notes(text):
    try:
        notes = json.loads(text.strip().removeprefix('```json').removeprefix('```').removesuffix('```'))['research_notes']
        return {key: [value[:200] for value in notes.get(key, [])[:12] if isinstance(value, str)]
                for key in ('queries', 'checked_sites', 'next_queries', 'part_references', 'remaining_gaps')
                if isinstance(notes.get(key, []), list)}
    except (ValueError, KeyError, TypeError, AttributeError):
        return {}


def run_research(job, run_round, refresh_exclusions, save_progress):
    started = time.monotonic()
    listings, summaries, sources, notes, rounds = [], [], [], {}, []
    tokens, usage_complete, observed = 0, True, False
    stop_reason = 'Round limit reached.'
    target = job.get('preferred_options', 6)
    excluded = job.get('excluded_listings', [])
    for index in range(MAX_ROUNDS):
        elapsed = time.monotonic() - started
        if elapsed >= TOTAL_SECONDS:
            stop_reason = 'Time budget reached.'
            break
        if tokens >= TOKEN_BUDGET:
            stop_reason = 'Reported token budget reached.'
            break
        excluded = refresh_exclusions()
        blocked = exclusion_keys(excluded)
        # A user can remove a listing while the provider is working.
        listings = [item for item in listings if listing_key(item['url']) not in blocked]
        prior = [{'url': item['url'], 'reason': 'Already found in this search.'} for item in listings]
        round_exclusions = prior + excluded
        compact = compact_exclusions(round_exclusions)
        round_job = dict(job, excluded_listings=compact,
                         preferred_options=target - len(listings),
                         research_round={
                             'number': index + 1, 'max_rounds': MAX_ROUNDS,
                             'strategy': ('Check priority sites in order AND run unrestricted web searches.',
                                          'Find new sellers using reference variants, synonyms and regional languages; cover unvisited priority sites AND the open web.',
                                          'Fill remaining gaps with alternative queries and specialist breakers; verify only promising new listings.')[index],
                             'previous_research': dict(notes),
                             'excluded_count': len(round_exclusions),
                             'exclusions_omitted': len(round_exclusions) - len(compact),
                             'max_search_queries': 6, 'max_listing_pages': 8,
                             'output_token_target': MAX_OUTPUT_TOKENS,
                         },
                         round_timeout_seconds=min(ROUND_SECONDS, TOTAL_SECONDS - elapsed))
        save_progress({'rounds': rounds, 'current_round': index + 1, 'max_rounds': MAX_ROUNDS,
                       'new_listings': len(listings), 'reported_tokens': tokens})
        try:
            result = run_round(round_job)
        except Exception:
            if not rounds:
                raise
            usage_complete = False
            rounds.append({'number': index + 1, 'new_listings': 0, 'filtered_listings': 0,
                           'reported_tokens': None, 'remote_url': '', 'status': 'failed'})
            stop_reason = 'A later round failed; earlier results were retained.'
            break
        summary, candidates = parse_research(result['result'])
        # Refresh again after the remote call, not just at queue time.
        excluded = refresh_exclusions()
        blocked = exclusion_keys(excluded)
        listings = [item for item in listings if listing_key(item['url']) not in blocked]
        already_seen = blocked | {listing_key(item['url']) for item in listings}
        summary = remove_excluded_links(summary, already_seen)
        added = 0
        candidates.sort(key=lambda item: (item['fitment_status'] == 'supported',
                                         item['availability'] == 'listed_available',
                                         item['visual_status'] == 'compared'), reverse=True)
        for item in candidates:
            key = listing_key(item['url'])
            if key in already_seen or len(listings) >= target:
                continue
            already_seen.add(key)
            listings.append(item)
            added += 1
        if summary.strip() and summary[:8000] not in summaries:
            summaries.append(summary[:8000])
        for url in result.get('sources', []):
            if public_url(url) and listing_key(url) not in blocked and url not in sources:
                sources.append(url)
        observed = observed or result.get('web_search_observed', False)
        usage = result.get('total_tokens')
        if isinstance(usage, int) and not isinstance(usage, bool) and usage >= 0:
            tokens += usage
        else:
            usage_complete = False
        rounds.append({'number': index + 1, 'new_listings': added, 'filtered_listings': len(candidates) - added,
                       'reported_tokens': usage, 'remote_url': result.get('remote_url', ''), 'status': 'completed'})
        new_notes = research_notes(result['result'])
        for key, values in new_notes.items():
            notes[key] = list(dict.fromkeys(notes.get(key, []) + values))[-16:]
        notes['last_round_new_listings'] = added
        if len(listings) >= target:
            stop_reason = 'Requested number of new options reached.'
            break
        if not result.get('web_search_observed'):
            stop_reason = 'Provider returned no evidence of web search.'
            break
        if index > 0 and added == 0:
            stop_reason = 'No new listings in the follow-up round.'
            break
    blocked = exclusion_keys(refresh_exclusions())
    listings = [item for item in listings if listing_key(item['url']) not in blocked]
    listings.sort(key=lambda item: (item['fitment_status'] == 'supported',
                                   item['availability'] == 'listed_available',
                                   item['visual_status'] == 'compared'), reverse=True)
    summary = remove_excluded_links('\n\n'.join(summaries), blocked)
    if not listings:
        summary = 'No new eligible listings found. Existing and blocked listings were excluded.\n\n' + summary
    meta = {'rounds': rounds, 'max_rounds': MAX_ROUNDS, 'new_listings': len(listings),
            'reported_tokens': tokens, 'usage_complete': usage_complete, 'token_budget': TOKEN_BUDGET,
            'stop_reason': stop_reason}
    return {'result': summary, 'listings': listings, 'sources': [url for url in sources[:60] if listing_key(url) not in blocked],
            'web_search_observed': observed, 'research_meta': meta}
