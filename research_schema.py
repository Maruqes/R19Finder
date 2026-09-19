"""Strict final-output contract for Codex; Open WebUI uses the same prompt contract."""


def object_schema(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


listing = {field: {'type': ['string', 'null']} for field in (
    'title', 'url', 'image_url', 'description', 'price', 'seller', 'location',
    'condition', 'shipping_cost', 'compatibility', 'visual_comparison',
    'variant_checks', 'availability_evidence')}
for field, options in {
    'pickup': ['available', 'unavailable', 'unknown'],
    'shipping': ['available', 'unavailable', 'unknown'],
    'visual_status': ['compared', 'inconclusive', 'not_checked'],
    'availability': ['listed_available', 'unknown', 'sold', 'reserved', 'unavailable'],
    'fitment_status': ['supported', 'uncertain', 'incompatible'],
}.items():
    listing[field] = {'type': 'string', 'enum': options}

RESEARCH_SCHEMA = object_schema({
    'summary_markdown': {'type': 'string'},
    'listings': {'type': 'array', 'items': object_schema(listing)},
    'research_notes': object_schema({key: {'type': 'array', 'items': {'type': 'string'}}
                                    for key in ('queries', 'checked_sites', 'next_queries',
                                                'part_references', 'remaining_gaps')}),
})
