"""Inspect the React bootstrap contract without asserting obsolete Jinja markup."""
import json
import re


def page_data(response):
    if hasattr(response, 'is_json') and response.is_json:
        return response.json['data']
    text = response.get_data(as_text=True) if hasattr(response, 'get_data') else response
    if isinstance(text, bytes):
        text = text.decode()
    match = re.search(r'<script id="page-data" type="application/json">(.*?)</script>', text, re.S)
    if not match:
        raise AssertionError('React bootstrap payload missing')
    return json.loads(match.group(1))['data']
