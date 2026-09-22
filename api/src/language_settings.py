from frontend import render_page as render_template
"""Installation-wide output and discovery languages, snapshotted per AI task."""
from flask import Blueprint, flash, redirect, request, url_for
from psycopg.types.json import Jsonb

LANGUAGES = {'en': 'English', 'pt': 'Português', 'fr': 'Français', 'de': 'Deutsch', 'es': 'Español'}
ENGLISH_NAMES = {'en': 'English', 'pt': 'Portuguese', 'fr': 'French', 'de': 'German', 'es': 'Spanish'}
DEFAULT_LANGUAGES = list(LANGUAGES)


def validate_preferences(response_language, search_languages):
    if not isinstance(response_language, str) or response_language not in LANGUAGES:
        raise ValueError('Choose a supported response language.')
    if not isinstance(search_languages, list) or not search_languages or len(search_languages) > 5 or any(not isinstance(v, str) or v not in LANGUAGES for v in search_languages):
        raise ValueError('Choose at least one supported search language.')
    if len(set(search_languages)) != len(search_languages):
        raise ValueError('Choose each language only once.')
    return {'response_language': response_language, 'search_languages': search_languages}


def get_preferences(conn):
    row = conn.execute('SELECT response_language,search_languages FROM language_preferences WHERE id=1').fetchone()
    return dict(row) if row else {'response_language': 'en', 'search_languages': DEFAULT_LANGUAGES.copy()}


def language_context(preferences=None):
    prefs = preferences or {'response_language': 'en', 'search_languages': DEFAULT_LANGUAGES}
    return {**prefs, 'response_language_name': ENGLISH_NAMES[prefs['response_language']],
            'search_language_names': [ENGLISH_NAMES[code] for code in prefs['search_languages']]}


LANGUAGE_RULES = '''Follow language_preferences. Write explanations, questions, fitment notes and summaries in response_language_name.
Generate real automotive search terms and aliases in EACH selected search language, with language labels.
Use those languages in actual queries, not merely in translated output. Preserve original reference codes,
manufacturer names, engine codes, URLs and source quotations; never translate or alter identifier digits.
Keep JSON keys and schema enum tokens unchanged; only human-readable text is translated.
A search language is not a country or shipping restriction. Do not exclude an exact matching source merely
because it is in another language. Report gaps when query/time budgets prevent covering a language.
'''


def create_settings_blueprint(connect, validate_csrf):
    bp = Blueprint('preferences', __name__)

    @bp.route('/settings', methods=['GET', 'POST'])
    def settings():
        error = None
        with connect() as conn:
            prefs = get_preferences(conn)
        if request.method == 'POST':
            validate_csrf()
            try:
                prefs = validate_preferences(request.form.get('response_language'), request.form.getlist('search_languages'))
                with connect() as conn:
                    conn.execute('UPDATE language_preferences SET response_language=%s,search_languages=%s WHERE id=1',
                                 (prefs['response_language'], Jsonb(prefs['search_languages'])))
                flash('Language preferences saved. New AI fills and searches will use them, including scheduled searches.')
                return redirect(url_for('preferences.settings'), code=303)
            except ValueError as exc:
                error = str(exc)
                prefs = {'response_language': request.form.get('response_language'), 'search_languages': request.form.getlist('search_languages')}
        return render_template('settings.html', preferences=prefs, languages=LANGUAGES, error=error), 400 if error else 200
    return bp
