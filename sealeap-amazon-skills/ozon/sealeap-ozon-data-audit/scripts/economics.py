#!/usr/bin/env python3
"""Linear CNY/RUB scenario calculator, not an accounting or autonomous trading tool."""
import argparse
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

from audit import check, strict_load, GATES

COST_FIELDS = ('seller_price', 'revenue_basis', 'procurement', 'domestic_shipping', 'packaging',
               'fx_rub_per_cny', 'outbound_shipping', 'return_loss', 'other_fixed',
               'commission_rate', 'payment_rate', 'tax_rate', 'ad_rate')
ROUTE_FIELDS = ('weight_kg', 'length_cm', 'width_cm', 'height_cm', 'volumetric_divisor',
                'max_billable_kg', 'delivery_days', 'max_delivery_days')
TRIAL_FIELDS = ('loss_cap', 'test_units', 'review_on', 'stop_condition')
FORMULAS = {
    'seller_price_rub': 'P', 'goods_cost_rub': 'G=(procurement+domestic_shipping+packaging)*fx',
    'fixed_cost_rub': 'F=G+outbound_shipping+return_loss+other_fixed',
    'merchandise_gross_profit_rub': 'P-G', 'contribution_before_ads_rub': 'P*(1-commission-payment-tax)-F',
    'contribution_after_ads_rub': 'P*(1-commission-payment-tax-ad)-F',
    'contribution_margin': '(P*(1-commission-payment-tax-ad)-F)/P',
    'break_even_price_rub': 'F/(1-commission-payment-tax-ad)',
    'break_even_ad_rate': '(P*(1-commission-payment-tax)-F)/P',
    'modeled_spend_rub': 'F+P*(commission+payment+tax+ad)'
}
SCENARIO = {'price_factor': '0.90', 'fx_factor': '1.10', 'shipping_factor': '1.20',
            'return_factor': '1.50'}


def rounded(value):
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def calculate(record, stressed=False):
    """Requires audited inputs; all rates have the same gross seller revenue base."""
    fields = record['fields']
    def n(key):
        return Decimal(str(fields[key]['value']))
    price, fx, shipping, returns = (n(k) for k in ('seller_price', 'fx_rub_per_cny', 'outbound_shipping', 'return_loss'))
    if stressed:
        price *= Decimal(SCENARIO['price_factor'])
        fx *= Decimal(SCENARIO['fx_factor'])
        shipping *= Decimal(SCENARIO['shipping_factor'])
        returns *= Decimal(SCENARIO['return_factor'])
    goods = (n('procurement') + n('domestic_shipping') + n('packaging')) * fx
    fixed = goods + shipping + returns + n('other_fixed')
    rates = n('commission_rate') + n('payment_rate') + n('tax_rate')
    denominator = 1 - rates - n('ad_rate')
    if denominator <= 0:
        return {'scenario_signal': 'NO-GO', 'reason': 'combined_rates_at_least_one', 'metrics': {}}
    before_ads = price * (1 - rates) - fixed
    contribution = before_ads - price * n('ad_rate')
    values = {'seller_price_rub': price, 'goods_cost_rub': goods, 'fixed_cost_rub': fixed, 'modeled_spend_rub': fixed + price * (rates + n('ad_rate')),
              'merchandise_gross_profit_rub': price - goods, 'contribution_before_ads_rub': before_ads,
              'contribution_after_ads_rub': contribution, 'contribution_margin': contribution / price if price else Decimal(0),
              'break_even_price_rub': fixed / denominator,
              'break_even_ad_rate': before_ads / price if price else Decimal(0)}
    return {'scenario_signal': 'GO' if contribution > 0 else 'NO-GO',
            'reason': 'positive_contribution' if contribution > 0 else 'nonpositive_contribution',
            'metrics': {k: rounded(v) for k, v in values.items()}}


def evaluate(document, as_of, max_age_days=7):
    audit = check(document, as_of, COST_FIELDS, max_age_days)
    if not isinstance(document, dict):
        return {'decision': 'HOLD', 'audit': audit}
    result = {'result_version': 'ozon-result/1.0', 'dataset_id': document.get('dataset_id'),
              'synthetic': document.get('synthetic'), 'skill': 'sealeap-ozon-unit-economics',
              'as_of': as_of.isoformat(), 'scope': document.get('context'), 'decision': 'HOLD',
              'decision_scope': 'numeric scenario and partial route checks; human business review required',
              'confidence': 'UNKNOWN', 'evidence_refs': [], 'metrics': {},
              'missing_fields': audit['missing_fields'], 'conflicts': document.get('conflicts', []),
              'limitations': ['No live fee/eligibility verification. Synthetic outputs cannot authorize a real trial.',
                              'Linear rates only; thresholds, refunds and different fee bases require a separate model.'],
              'next_actions': [], 'audit': audit, 'records': []}
    if audit['status'] == 'HOLD':
        result['next_actions'] = [{'action': 'resolve audit errors and missing cost evidence',
                                   'owner': 'analyst', 'recovery_condition': 'all required inputs validated'}]
        return result
    for record in document['records']:
        if record['role'] != 'candidate':
            continue
        fields = record['fields']
        output = {'record_id': record['record_id'], 'scenario_signal': 'HOLD', 'missing_fields': [],
                  'decision': 'HOLD', 'reasons': [], 'base': {}, 'stress': {}, 'route': {}}
        if fields['revenue_basis']['value'] != 'gross_seller':
            output['reasons'].append('unsupported_revenue_basis_or_double_deduction')
            result['records'].append(output)
            continue
        output['base'], output['stress'] = calculate(record), calculate(record, True)
        output['scenario_signal'] = ('GO' if all(output[s]['scenario_signal'] == 'GO' for s in ('base', 'stress')) else 'NO-GO')
        required = ROUTE_FIELDS + TRIAL_FIELDS + tuple(sorted(GATES))
        output['missing_fields'] = [k for k in required if k not in fields or fields[k]['kind'] == 'UNKNOWN']
        proven_failures = [k for k in GATES if k in fields and fields[k]['kind'] == 'FACT' and fields[k]['value'] is False]
        uncertain_gates = [k for k in GATES if k in fields and fields[k]['kind'] not in ('FACT', 'UNKNOWN')]
        output['reasons'].extend('unverified_gate:' + k for k in uncertain_gates)
        if not any(k in output['missing_fields'] for k in ROUTE_FIELDS):
            def n(k): return Decimal(str(fields[k]['value']))
            volumetric = n('length_cm') * n('width_cm') * n('height_cm') / n('volumetric_divisor')
            billable = max(n('weight_kg'), volumetric)
            output['route'] = {'volumetric_kg': rounded(volumetric), 'billable_kg': rounded(billable)}
            verified_route = all(fields[k]['kind'] == 'FACT' for k in ROUTE_FIELDS)
            if verified_route and billable > n('max_billable_kg'):
                proven_failures.append('route_weight_limit')
            if verified_route and n('delivery_days') > n('max_delivery_days'):
                proven_failures.append('route_delivery_limit')
            # Measurement and contract limits are hard inputs, not scenario assumptions.
            if any(fields[k]['kind'] != 'FACT' for k in ROUTE_FIELDS):
                output['reasons'].append('route_inputs_not_verified')
        if not any(k in output['missing_fields'] for k in TRIAL_FIELDS):
            try:
                if date.fromisoformat(str(fields['review_on']['value'])) <= as_of:
                    output['reasons'].append('review_date_not_future')
            except ValueError:
                output['reasons'].append('invalid_review_date')
            if not isinstance(fields['stop_condition']['value'], str) or not fields['stop_condition']['value'].strip():
                output['reasons'].append('missing_stop_condition')
            # Conservative modeled spending check, not a full cash-flow forecast.
            fixed = output['stress']['metrics'].get('modeled_spend_rub')
            if fixed is None or Decimal(str(fixed)) * Decimal(str(fields['test_units']['value'])) > Decimal(str(fields['loss_cap']['value'])):
                output['reasons'].append('trial_funding_exceeds_loss_cap')
        output['reasons'].extend(proven_failures)
        if output['scenario_signal'] == 'NO-GO' or proven_failures:
            output['decision'] = 'NO-GO'
        elif not output['missing_fields'] and not output['reasons']:
            output['decision'] = 'GO'
        output['stress_assumptions'] = SCENARIO
        output['metric_kind'] = 'ESTIMATE'
        output['input_refs'] = [record['record_id'] + ':' + k for k in COST_FIELDS]
        output['formula'] = '(price*(1-commission-payment-tax-ad)) - ((procurement+domestic+packaging)*fx+outbound+return_loss+other_fixed)'
        all_input_refs = [record['record_id'] + ':' + k for k in fields]
        result['evidence_refs'].extend(all_input_refs)
        result['missing_fields'][record['record_id']] = output['missing_fields']
        all_sources = sorted({sid for k in COST_FIELDS for sid in fields[k]['source_ids']})
        for scenario_name in ('base', 'stress'):
            for metric_name, value in output[scenario_name]['metrics'].items():
                is_money = metric_name.endswith('_rub')
                result['metrics'][record['record_id'] + ':' + scenario_name + ':' + metric_name] = {
                    'value': value, 'kind': 'ESTIMATE', 'unit': 'money' if is_money else 'ratio',
                    'currency': 'RUB' if is_money else None, 'source_ids': all_sources,
                    'raw_fields': output['input_refs'], 'confidence': 'LOW',
                    'reason': 'derived scenario, not realized profit', 'formula': FORMULAS[metric_name],
                    'input_refs': output['input_refs']}

        result['records'].append(output)
    decisions = [r['decision'] for r in result['records']]
    result['decision'] = ('GO' if decisions and all(d == 'GO' for d in decisions) else
                          'NO-GO' if decisions and all(d == 'NO-GO' for d in decisions) else 'HOLD')
    confidence_order = {'UNKNOWN': 0, 'LOW': 1, 'MEDIUM': 2, 'HIGH': 3}
    confidence = [f['confidence'] for r in document['records'] if r['role'] == 'candidate'
                  for k, f in r['fields'].items() if k in COST_FIELDS + ROUTE_FIELDS + TRIAL_FIELDS + tuple(GATES)]
    if confidence:
        result['confidence'] = min(confidence, key=confidence_order.get)
    if result['decision'] == 'HOLD':
        result['next_actions'] = [{'action': 'resolve per-record missing_fields/reasons; review source originals',
                                  'owner': 'seller', 'recovery_condition': 'verified costs, route and bounded trial'}]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--as-of', required=True, type=date.fromisoformat)
    args = parser.parse_args()
    try:
        result = evaluate(strict_load(args.input), args.as_of)
    except (ValueError, OSError) as exc:
        result = {'decision': 'HOLD', 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if result['decision'] == 'HOLD' else 0


if __name__ == '__main__':
    raise SystemExit(main())
