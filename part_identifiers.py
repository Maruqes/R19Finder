"""Concrete part identifiers and evidence requirements, separate from part names."""
import re
from urllib.parse import urlsplit

KINDS = ('oem', 'manufacturer', 'casting', 'catalogue', 'supersession', 'other')
IDENTIFIER_SCHEMA = {
    'type': ['object', 'null'], 'additionalProperties': False,
    'properties': {
        'code': {'type': 'string'}, 'kind': {'type': 'string', 'enum': list(KINDS)},
        'manufacturer': {'type': 'string'},
        'match': {'type': 'string', 'enum': ['supported', 'candidate']},
        'matched_attributes': {'type': 'array', 'items': {'type': 'string'}},
        'unresolved_attributes': {'type': 'array', 'items': {'type': 'string'}}
    },
    'required': ['code', 'kind', 'manufacturer', 'match', 'matched_attributes', 'unresolved_attributes']
}


def validate_identifier(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('Invalid part identifier.')
    code = value.get('code')
    if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ./_+():-]{1,79}', code.strip()):
        raise ValueError('A part identifier must contain a concrete code of 2–80 characters.')
    if not isinstance(value.get('kind'), str) or value['kind'] not in KINDS or value.get('match') not in ('supported', 'candidate'):
        raise ValueError('Invalid identifier type or match status.')
    maker = value.get('manufacturer', '')
    if not isinstance(maker, str) or len(maker) > 150:
        raise ValueError('Invalid identifier manufacturer.')
    result = dict(code=code.strip(), kind=value['kind'], manufacturer=maker.strip(), match=value['match'])
    for key in ('matched_attributes', 'unresolved_attributes'):
        items = value.get(key, [])
        if not isinstance(items, list) or len(items) > 12 or any(not isinstance(item, str) or len(item) > 300 for item in items):
            raise ValueError('Invalid identifier fitment evidence.')
        result[key] = [item.strip() for item in items if item.strip()]
    return result


def evidence_key(url):
    try:
        parsed = urlsplit(url)
        return parsed.netloc.lower(), parsed.path.rstrip('/'), parsed.query
    except ValueError:
        return None


def eligible_reference(fact, observed_sources, web_observed):
    """Accept only concrete, sourced identifiers; never equate model recall to research."""
    identifier = fact.get('identifier')
    evidence = [e for e in fact.get('evidence', []) if e.get('url') and e.get('note', '').strip()]
    if not web_observed or not identifier or not evidence:
        return False
    observed = {evidence_key(url) for url in observed_sources}
    linked = any(evidence_key(e['url']) in observed for e in evidence)
    # A citation is not independent verification. Absence of recorded tool sources,
    # unresolved attributes, or no actual variant match always makes this a candidate.
    if not linked or not identifier['matched_attributes'] or identifier['unresolved_attributes']:
        identifier['match'] = 'candidate'
    return True


IDENTIFIER_RULES = '''Investigate the exact physical part and variant, not generic references for the vehicle model.
Look for OEM numbers, manufacturer product codes, casting/engineering marks, catalogue IDs and documented supersessions.
Search manufacturer catalogues, parts diagrams and specialist product pages using description, car specifications,
existing codes and photos together. Distinguish a lamp assembly from its lens/bulb holder, left from right,
phase/generation, body style, build years, engine and relevant mountings/connectors.
For EVERY references suggestion provide identifier metadata with the literal code, type, manufacturer,
matched attributes and unresolved attributes, plus source URLs with notes explaining what each source establishes.
A catalogue or listing for a similar car is not proof of this part's identifier. Keep incomplete matches as candidate.
A URL is not a part identifier. Generic part names and translated descriptions belong in aliases, not references.
Do not invent a code when no exact identifier is found. Return a concrete missing-information question instead.
Never infer codes from visual similarity or manufacture alternate codes by changing suffixes/digits.
Do not label aftermarket or casting numbers as OEM. Document supersession direction and applicable variants.
'''
