"""Validate optional structured research output without fetching seller URLs."""
import ipaddress
import json
import hashlib
from urllib.parse import urlsplit, parse_qsl, urlencode


def listing_key(url):
    """Ignore fragments and common tracking parameters, not product identifiers."""
    parts = urlsplit(url)
    query = sorted((key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                   if not key.lower().startswith('utm_') and key.lower() not in {'fbclid', 'gclid'})
    normalized = parts._replace(netloc=parts.netloc.lower(), fragment='', query=urlencode(query)).geturl()
    return hashlib.sha256(normalized.encode()).hexdigest()


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
        url = public_url(item.get('url'))
        if not url:
            continue
        clean = {key: item[key].strip()[:1500] if isinstance(item.get(key), str) else ''
                 for key in ('title', 'description', 'price', 'seller', 'location',
                             'condition', 'shipping_cost', 'compatibility',
                             'visual_comparison', 'variant_checks', 'availability_evidence')}
        clean['availability'] = ('listed_available' if item.get('availability') == 'listed_available'
                                 and clean['availability_evidence'] else 'unknown')
        status = item.get('visual_status')
        clean['visual_status'] = status if status in ('compared', 'inconclusive', 'not_checked') else 'not_checked'
        clean.update(url=url, image_url=public_url(item.get('image_url'), image=True))
        for key in ('pickup', 'shipping'):
            clean[key] = item.get(key) if item.get(key) in ('available', 'unavailable', 'unknown') else 'unknown'
        listings.append(clean)
    return payload['summary_markdown'], listings
