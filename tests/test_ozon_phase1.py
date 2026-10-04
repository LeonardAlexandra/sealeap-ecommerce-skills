"""Reproducible phase-one evidence/decision regressions; never contacts live accounts."""
import copy
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'sealeap-amazon-skills/ozon/sealeap-ozon-data-audit'
CASES = AUDIT / 'references/cases'
sys.path.insert(0, str(AUDIT / 'scripts'))
from audit import check, strict_load
from economics import evaluate, COST_FIELDS
from market import descriptive_market

AS_OF = date(2026, 10, 4)
EXPECTED = strict_load(CASES / 'expected.json')['cases']


class PhaseOneTests(unittest.TestCase):
    def setUp(self):
        self.doc = strict_load(CASES / '01-bounded-trial.json')
        self.fields = self.doc['records'][0]['fields']

    def audit(self, **kwargs):
        return check(self.doc, AS_OF, **kwargs)

    def blocked(self, reason):
        result = self.audit(required=COST_FIELDS)
        self.assertEqual(result['status'], 'HOLD', result)
        self.assertTrue(any(reason in e for e in result['errors']), result)

    def test_five_cases_match_independent_arithmetic_and_decisions(self):
        for expected in EXPECTED:
            with self.subTest(case=expected['id']):
                doc = strict_load(CASES / (expected['id'] + '.json'))
                result = evaluate(doc, AS_OF)
                self.assertEqual(result['audit']['status'], expected['audit'])
                self.assertEqual(result['decision'], expected['decision'])
                self.assertIs(result['synthetic'], True)
                if 'base_contribution' in expected:
                    row = result['records'][0]
                    self.assertAlmostEqual(row['base']['metrics']['contribution_after_ads_rub'], expected['base_contribution'])
                    self.assertAlmostEqual(row['stress']['metrics']['contribution_after_ads_rub'], expected['stress_contribution'])
                    self.assertEqual(row['route']['billable_kg'], expected['billable_kg'])
                else:
                    self.assertEqual(result['metrics'], {})

    def test_no_mpstats_needed_for_bounded_trial(self):
        self.assertNotIn('mpstats', [s['provider'] for s in self.doc['sources']])
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'GO')

    def test_all_case_raw_files_have_matching_hashes(self):
        for expected in EXPECTED:
            doc = strict_load(CASES / (expected['id'] + '.json'))
            result = check(doc, AS_OF, source_root=CASES)
            self.assertFalse(any('raw_' in e for e in result['errors']), result)

    def test_changed_raw_file_is_rejected(self):
        self.doc['sources'][0]['raw_sha256'] = 'a' * 64
        result = self.audit(source_root=CASES)
        self.assertIn('raw_hash_mismatch:cny-costs', result['errors'])

    def test_source_path_cannot_escape_root(self):
        self.doc['sources'][0]['locator'] = '../schema.json'
        self.assertIn('raw_file_unavailable:cny-costs', self.audit(source_root=CASES)['errors'])

    def test_comment_counts_do_not_create_sales(self):
        market = descriptive_market(self.doc)
        self.assertIsNone(market['market_size']['value'])
        self.assertIsNone(market['sales_cr5']['value'])
        self.assertIsNone(market['sales_weighted_price']['value'])
        self.assertEqual(market['seller_listing_counts'], {'seller-a': 2, 'seller-b': 1})

    def test_price_normalization_and_median_are_reproducible(self):
        group = descriptive_market(self.doc)['groups']['organizer-small']
        self.assertEqual(group, {'sample_n': 3, 'median_rub_per_unit': 600, 'min': 500, 'max': 700})

    def test_ozon_card_price_does_not_change_seller_profit(self):
        baseline = evaluate(self.doc, AS_OF)['records'][0]['base']['metrics']
        for row in self.doc['records'][1:]:
            row['fields']['price_card']['value'] = 1
        self.assertEqual(evaluate(self.doc, AS_OF)['records'][0]['base']['metrics'], baseline)

    def test_incomparable_specs_are_not_mixed(self):
        self.doc['records'][1]['spec_group'] = 'accessory'
        groups = descriptive_market(self.doc)['groups']
        self.assertEqual(groups['accessory']['sample_n'], 1)
        self.assertEqual(groups['organizer-small']['median_rub_per_unit'], 650)

    def test_duplicate_competitors_not_counted_twice(self):
        self.doc['records'].append(copy.deepcopy(self.doc['records'][1]))
        with self.assertRaises(ValueError):
            descriptive_market(self.doc)

    def test_unknown_seller_not_merged_into_fake_giant_seller(self):
        self.doc['records'][1]['seller_id'] = None
        self.assertEqual(descriptive_market(self.doc)['seller_listing_counts'], {'seller-a': 1, 'seller-b': 1})

    def test_missing_cost_is_not_zero(self):
        del self.fields['outbound_shipping']
        result = evaluate(self.doc, AS_OF)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertIn('outbound_shipping', result['missing_fields']['candidate'])
        self.assertEqual(result['metrics'], {})

    def test_explicit_verified_zero_fee_is_allowed(self):
        self.fields['tax_rate']['value'] = 0
        self.assertEqual(self.audit()['status'], 'VALID_SYNTHETIC')

    def test_unknown_field_cannot_hold_nonnull_value(self):
        self.fields['procurement']['kind'] = 'UNKNOWN'
        self.blocked('schema')

    def test_zero_quantity_rejected(self):
        self.doc['records'][1]['fields']['pack_quantity']['value'] = 0
        self.blocked('nonpositive')

    def test_invalid_numeric_inputs_rejected(self):
        for value in (True, '20', -1, float('nan'), float('inf'), 10 ** 1000):
            with self.subTest(value_type=type(value).__name__):
                self.fields['procurement']['value'] = value
                self.blocked('invalid_number')

    def test_boolean_cannot_replace_trial_count(self):
        self.fields['test_units']['value'] = True
        self.blocked('invalid_number')

    def test_bad_currency_rejected(self):
        self.fields['procurement']['currency'] = 'RUB'
        self.blocked('wrong_currency')

    def test_unknown_source_unit_rejected(self):
        self.doc['sources'][0]['money_unit'] = 'UNKNOWN'
        self.blocked('unknown_money_unit')

    def test_minor_units_need_documented_conversion(self):
        self.doc['sources'][0]['money_unit'] = 'minor'
        self.blocked('missing_unit_conversion')

    def test_fx_zero_or_wrong_direction_rejected(self):
        self.fields['fx_rub_per_cny']['value'] = 0
        self.blocked('nonpositive')
        self.fields['fx_rub_per_cny']['value'] = 12
        self.fields['fx_rub_per_cny']['unit'] = 'CNY/RUB'
        self.blocked('wrong_unit')

    def test_net_settlement_does_not_get_fees_deducted_twice(self):
        self.fields['revenue_basis']['value'] = 'net_settlement'
        result = evaluate(self.doc, AS_OF)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertIn('unsupported_revenue_basis_or_double_deduction', result['records'][0]['reasons'])

    def test_nonpositive_break_even_denominator(self):
        self.fields['commission_rate']['value'] = 0.9
        self.fields['ad_rate']['value'] = 0.2
        result = evaluate(self.doc, AS_OF)
        self.assertEqual(result['decision'], 'NO-GO')
        self.assertEqual(result['records'][0]['base']['metrics'], {})

    def test_hard_gate_cannot_be_an_assumption(self):
        self.fields['compliance_verified']['kind'] = 'ASSUMPTION'
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'HOLD')

    def test_verified_unavailable_account_is_no_go(self):
        self.fields['account_eligible']['value'] = False
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'NO-GO')

    def test_unverified_route_cannot_be_passed_or_called_proven_failure(self):
        self.fields['weight_kg']['value'] = 99
        self.fields['weight_kg']['kind'] = 'ASSUMPTION'
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'HOLD')

    def test_late_route_is_no_go(self):
        self.fields['delivery_days']['value'] = 40
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'NO-GO')

    def test_missing_return_evidence_blocks_profit(self):
        del self.fields['return_loss']
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'HOLD')

    def test_trial_requires_budget_and_future_review(self):
        self.fields['loss_cap']['value'] = 10
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'HOLD')
        self.fields['loss_cap']['value'] = 5000
        self.fields['review_on']['value'] = '2026-10-03'
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'HOLD')

    def test_local_success_does_not_override_crossborder_limit(self):
        doc = strict_load(CASES / '03-local-hit-crossborder-fail.json')
        result = evaluate(doc, AS_OF)['records'][0]
        self.assertEqual(result['scenario_signal'], 'GO')
        self.assertEqual(result['decision'], 'NO-GO')
        self.assertIn('route_weight_limit', result['reasons'])

    def test_stale_period_not_refreshed_by_redownload(self):
        self.doc['sources'][0]['period_start'] = '2026-08-01'
        self.doc['sources'][0]['period_end'] = '2026-08-31'
        self.blocked('stale_source')

    def test_future_capture_and_invalid_timezone_rejected(self):
        self.doc['sources'][0]['captured_at'] = '2026-10-06T12:00:00+08:00'
        self.blocked('invalid_source_time')
        self.doc['sources'][0]['timezone'] = 'not-a-zone'
        self.blocked('invalid_source_time')

    def test_incomplete_market_coverage_rejected_but_sample_allowed(self):
        self.doc['sources'][3]['scope'] = 'declared_market'
        self.doc['sources'][3]['coverage']['total'] = 1000
        self.blocked('incomplete_market_scope')
        self.doc['sources'][3]['scope'] = 'sample'
        self.assertEqual(self.audit()['status'], 'VALID_SYNTHETIC')

    def test_duplicate_record_and_source_rejected(self):
        self.doc['records'].append(copy.deepcopy(self.doc['records'][0]))
        self.doc['sources'].append(copy.deepcopy(self.doc['sources'][0]))
        self.blocked('duplicate_record')
        self.blocked('duplicate_source')

    def test_fact_needs_source_and_raw_mapping(self):
        self.fields['procurement']['source_ids'] = []
        self.blocked('schema')
        self.fields['procurement']['source_ids'] = ['nonexistent']
        self.blocked('unknown_source')

    def test_missing_source_field_mapping_rejected(self):
        del self.doc['sources'][0]['field_map']['procurement']
        self.blocked('missing_field_mapping')

    def test_external_estimate_never_becomes_actual(self):
        f = copy.deepcopy(self.fields['seller_price'])
        f.update(value=100, kind='FACT', unit='count', currency=None, source_ids=['storefront'])
        self.fields['sales_estimate'] = f
        self.doc['sources'][3]['field_map']['sales_estimate'] = 'reviews'
        self.blocked('estimate_promoted_to_fact')
        f['kind'] = 'ESTIMATE'
        self.blocked('proxy_as_sales')

    def test_optional_estimate_can_be_added_without_changing_profit(self):
        other = strict_load(CASES / '05-conflicting-sources.json')
        source = next(s for s in other['sources'] if s['id'] == 'mpstats')
        self.doc['sources'].append(source)
        self.fields['sales_estimate'] = other['records'][0]['fields']['sales_estimate']
        result = evaluate(self.doc, AS_OF)
        self.assertEqual(result['decision'], 'GO')
        self.assertEqual(result['records'][0]['base']['metrics']['contribution_after_ads_rub'], 440)

    def test_unknown_extra_market_metric_does_not_block_cost_model(self):
        self.fields['sales_estimate'] = {'value': None, 'kind': 'UNKNOWN', 'unit': 'count',
            'currency': None, 'source_ids': [], 'raw_fields': [], 'confidence': 'UNKNOWN', 'reason': 'not available'}
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'GO')

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_literals(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'
            for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
                p.write_text(raw)
                with self.assertRaises(ValueError): strict_load(p)

    def test_malformed_top_level_fails_closed(self):
        self.assertEqual(evaluate([], AS_OF)['decision'], 'HOLD')
        self.assertEqual(evaluate({}, AS_OF)['decision'], 'HOLD')

    def test_copied_economics_skill_is_standalone(self):
        with tempfile.TemporaryDirectory() as tmp:
            import shutil
            target = Path(tmp) / 'skill'
            shutil.copytree(ROOT / 'sealeap-amazon-skills/ozon/sealeap-ozon-unit-economics', target)
            run = subprocess.run([sys.executable, str(target / 'scripts/economics.py'),
                                  str(target / 'references/standalone-example.json'), '--as-of', str(AS_OF)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['decision'], 'GO')

    def test_budget_includes_modeled_fees_and_ads(self):
        self.fields['loss_cap']['value'] = 5000
        result = evaluate(self.doc, AS_OF)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertEqual(result['records'][0]['stress']['metrics']['modeled_spend_rub'], 1115)

    def test_derived_metrics_have_specific_formulas_and_evidence(self):
        result = evaluate(self.doc, AS_OF)
        metric = result['metrics']['candidate:base:break_even_price_rub']
        self.assertEqual(metric['formula'], 'F/(1-commission-payment-tax-ad)')
        self.assertEqual(metric['kind'], 'ESTIMATE')
        self.assertEqual(metric['currency'], 'RUB')
        self.assertTrue(metric['source_ids'])
        self.assertTrue(metric['input_refs'])

    def test_nonfinancial_missing_fields_reach_result_envelope(self):
        del self.fields['weight_kg']
        result = evaluate(self.doc, AS_OF)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertIn('weight_kg', result['missing_fields']['candidate'])

    def test_optional_unknown_is_reported_without_blocking_other_work(self):
        self.fields['brand'] = {'value': None, 'kind': 'UNKNOWN', 'unit': 'text',
            'currency': None, 'source_ids': [], 'raw_fields': [], 'confidence': 'UNKNOWN', 'reason': 'not supplied'}
        self.assertIn('brand', self.audit()['unknown_fields']['candidate'])
        self.assertEqual(evaluate(self.doc, AS_OF)['decision'], 'GO')

    def test_unmigrated_skills_and_other_platforms_unchanged(self):
        migrated = {'sealeap-ozon-' + n for n in ('mpstats-data-audit', 'niche-screening',
                    'competitor-map', 'price-segment', 'unit-economics', 'fulfillment-choice')}
        changed = subprocess.check_output(['git', 'diff', '--name-only', 'e1a39e197193a07a044ca80191bf541eae17f4a5'],
                                          cwd=ROOT, text=True).splitlines()
        platforms = {'shopify', 'etsy', 'ebay', 'tiktokshop', 'walmart', 'mercadolibre', 'wayfair'}
        for name in changed:
            parts = Path(name).parts
            if len(parts) > 2 and parts[0] == 'sealeap-amazon-skills':
                self.assertNotIn(parts[1], platforms)
                if parts[1] == 'ozon':
                    self.assertIn(parts[2], migrated | {'sealeap-ozon-data-audit'})


if __name__ == '__main__':
    unittest.main()
