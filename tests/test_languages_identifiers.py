import json
import unittest
import uuid
from unittest.mock import Mock

from language_settings import validate_preferences, language_context, DEFAULT_LANGUAGES
from part_profile import parse_suggestions, enrichment_prompt
from part_identifiers import validate_identifier
from search import prompt_for
from research_loop import run_research


def reference(**changes):
    result = dict(field='references', value='00123-AB · manufacturer reference', reason='Matches this part and variant.',
                  identifier=dict(code='00123-AB', kind='manufacturer', manufacturer='Example', match='supported',
                                  matched_attributes=['Left rear lamp', 'Phase 1 saloon'], unresolved_attributes=[]),
                  evidence=[dict(url='https://example.com/catalogue/00123', note='Left rear lamp for the specified phase and body.')])
    result.update(changes)
    return result


class LanguageIdentifierTests(unittest.TestCase):
    def test_preferences_validation_and_default_five_languages(self):
        self.assertEqual(set(language_context()['search_languages']), {'en','pt','fr','de','es'})
        self.assertEqual(validate_preferences('pt', ['fr','de'])['response_language'], 'pt')
        for response, search in [('xx',['en']), ('en',[]), ('en',['xx']), ('en',['pt','pt'])]:
            with self.assertRaises(ValueError):
                validate_preferences(response, search)

    def test_prompts_use_response_and_query_languages_without_translating_codes(self):
        prefs = {'response_language':'pt', 'search_languages':['fr','de']}
        prompt = enrichment_prompt({'language_preferences': prefs, 'purpose':'identifiers'})
        self.assertIn('Portuguese', prompt); self.assertIn('German', prompt)
        self.assertIn('literal code', prompt); self.assertIn('references suggestions only', prompt)
        query = json.loads(prompt_for(dict(vehicle='R19',description='Lamp',instructions='',language_preferences=prefs)))
        self.assertEqual(query['language_preferences']['search_language_names'], ['French','German'])

    def test_no_invented_or_memory_only_reference_is_applied(self):
        for item, observed in [(reference(identifier=None), True), (reference(evidence=[]), True), (reference(), False)]:
            result = parse_suggestions(json.dumps({'suggestions':[item]}), uuid.uuid4(), web_observed=observed, purpose='identifiers', response_language='pt')
            self.assertEqual(result['suggestions'], [])
            self.assertIn('Não', result['limitations'][0])

    def test_source_matching_and_variant_gaps_downgrade_reference(self):
        item = reference()
        result = parse_suggestions(json.dumps({'suggestions':[item]}), uuid.uuid4(), web_observed=True)
        self.assertEqual(result['suggestions'][0]['identifier']['match'], 'candidate')
        result = parse_suggestions(json.dumps({'suggestions':[item]}), uuid.uuid4(), web_observed=True, observed_sources=['https://example.com/catalogue/00123'])
        fact = result['suggestions'][0]
        self.assertEqual(fact['identifier']['match'], 'supported')
        self.assertEqual(fact['verification_status'], 'unverified')
        self.assertEqual(fact['identifier']['code'], '00123-AB')
        item['identifier']['unresolved_attributes'] = ['Connector not confirmed']
        result = parse_suggestions(json.dumps({'suggestions':[item]}), uuid.uuid4(), web_observed=True, observed_sources=['https://example.com/catalogue/00123'])
        self.assertEqual(result['suggestions'][0]['identifier']['match'], 'candidate')

    def test_identifiers_only_task_does_not_change_unrelated_fields(self):
        result = parse_suggestions(json.dumps({'suggestions':[{'field':'name','value':'Lamp'}]}), uuid.uuid4(), purpose='identifiers')
        self.assertEqual(result['suggestions'], [])

    def test_actual_research_rounds_receive_selected_query_languages(self):
        def round_result(job):
            return {'result': json.dumps({'summary_markdown':'Nada.', 'listings':[]}), 'sources':[], 'web_search_observed':True, 'total_tokens':1}
        run = Mock(side_effect=round_result)
        job = {'preferred_options':6,'language_preferences':{'response_language':'pt','search_languages':['fr','de']}}
        output = run_research(job, run, lambda: [], lambda _: None)
        self.assertEqual(run.call_args_list[0].args[0]['research_round']['query_languages'], ['French','German'])
        self.assertEqual(run.call_args_list[1].args[0]['research_round']['query_languages'], ['German','French'])
        self.assertTrue(output['result'].startswith('Não'))
