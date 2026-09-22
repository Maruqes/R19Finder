"""Validate optional structured research output without fetching seller URLs."""
import ipaddress
import json
import hashlib
import re
from html import unescape
from urllib.parse import urlsplit, parse_qsl, urlencode


def listing_key(url):
    """Ignore fragments and common tracking parameters, not product identifiers."""
    parts = urlsplit(url)
    query = sorted((key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                   if not key.lower().startswith('utm_') and key.lower() not in {'fbclid', 'gclid'})
    normalized = parts._replace(netloc=parts.netloc.lower(), fragment='', query=urlencode(query)).geturl()
    return hashlib.sha256(normalized.encode()).hexdigest()


def excluded_for_request(conn, request_id):
    """Blacklist wins over history; exclusions stay scoped to this part request."""
    entries = conn.execute('SELECT url, reason FROM listing_blacklist WHERE request_id=%s ORDER BY created_at',
                           (request_id,)).fetchall()
    excluded = {listing_key(item['url']): dict(item) for item in entries}
    history = conn.execute("SELECT listings FROM searches WHERE request_id=%s AND status='completed' ORDER BY created_at DESC",
                           (request_id,)).fetchall()
    for row in history:
        for item in row['listings']:
            url = public_url(item.get('url'))
            if url:
                excluded.setdefault(listing_key(url), {'url': url, 'reason': 'Already in Parts Found.'})
    return list(excluded.values())


def exclusion_keys(excluded):
    return {listing_key(item['url']) for item in excluded if public_url(item.get('url'))}


def remove_excluded_links(text, blocked):
    """Drop paragraphs recommending excluded URLs, including Markdown and tracking variants."""
    paragraphs = []
    for paragraph in text.split('\n\n'):
        urls = re.findall(r'https?://[^\s<>"\)\]]+', unescape(paragraph))
        if not any(listing_key(url.rstrip('.,;')) in blocked for url in urls if public_url(url.rstrip('.,;'))):
            paragraphs.append(paragraph)
    return '\n\n'.join(paragraphs)


def public_url(value, image=False):
    if not isinstance(value, str) or len(value) > 2048:
        return ''
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower().rstrip('.')
        if (parts.scheme not in ({'https'} if image else {'http', 'https'})
                or parts.username or parts.password or not host or parts.port not in (None, 80, 443)
                or '.' not in host or host.endswith(('.local', '.localhost', '.internal', '.test'))):
            return ''
        try:
            if not ipaddress.ip_address(host).is_global:
                return ''
        except ValueError:
            pass
        return value
    except ValueError:
        return ''


def parse_research(text):
    """Keep ordinary Markdown intact when a provider ignores the JSON contract."""
    candidate = text.strip()
    if candidate.startswith('```') and candidate.endswith('```'):
        candidate = candidate.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:
        payload = json.loads(candidate)
    except (ValueError, TypeError):
        return text, []
    if (not isinstance(payload, dict) or not isinstance(payload.get('summary_markdown'), str)
            or not isinstance(payload.get('listings'), list)):
        return text, []
    listings = []
    for item in payload['listings'][:20]:
        if not isinstance(item, dict):
            continue
        if item.get('availability') in ('sold', 'reserved', 'unavailable'):
            continue
        if item.get('fitment_status') == 'incompatible':
            continue
        url = public_url(item.get('url'))
        if not url:
            continue
        clean = {key: item[key].strip()[:1500] if isinstance(item.get(key), str) else ''
                 for key in ('title', 'description', 'price', 'seller', 'location',
                             'condition', 'shipping_cost', 'compatibility',
                             'visual_comparison', 'variant_checks', 'availability_evidence')}
        clean['availability'] = ('listed_available' if item.get('availability') == 'listed_available'
                                 and clean['availability_evidence'] else 'unknown')
        clean['fitment_status'] = ('supported' if item.get('fitment_status') == 'supported'
                                   and clean['compatibility'] and clean['variant_checks'] else 'uncertain')
        status = item.get('visual_status')
        clean['visual_status'] = status if status in ('compared', 'inconclusive', 'not_checked') else 'not_checked'
        clean.update(url=url, image_url=public_url(item.get('image_url'), image=True))
        for key in ('pickup', 'shipping'):
            clean[key] = item.get(key) if item.get(key) in ('available', 'unavailable', 'unknown') else 'unknown'
        listings.append(clean)
    return payload['summary_markdown'], listings


def blacklist_part(conn, request_id, url, reason=''):
    """Shared web/Discord action, with the same request lock and URL normalization."""
    order = conn.execute('SELECT id FROM requests WHERE id=%s FOR UPDATE', (request_id,)).fetchone()
    if not order:
        raise LookupError('Request not found.')
    searches = conn.execute('SELECT listings FROM searches WHERE request_id=%s', (request_id,)).fetchall()
    listing = next((item for search in searches for item in search['listings'] if item.get('url') == url), None)
    if listing is None:
        raise LookupError('Listing not found.')
    conn.execute('''INSERT INTO listing_blacklist (request_id, url, url_key, title, reason)
        VALUES (%s, %s, %s, %s, %s) ON CONFLICT (request_id, url_key)
        DO UPDATE SET reason=EXCLUDED.reason''',
        (request_id, url, listing_key(url), listing.get('title', ''), reason))
