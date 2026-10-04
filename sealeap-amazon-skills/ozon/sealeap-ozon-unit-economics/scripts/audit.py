#!/usr/bin/env python3
"""Offline evidence contract checks. No authentication or proof of source truth."""
import argparse
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = Path(__file__).resolve().parents[1] / 'references/schema.json'
MONEY = {'price_regular', 'price_discount', 'price_card', 'seller_price', 'procurement',
         'domestic_shipping', 'packaging', 'outbound_shipping', 'return_loss', 'other_fixed',
         'loss_cap', 'revenue_estimate', 'revenue_actual'}
CNY = {'procurement', 'domestic_shipping', 'packaging'}
RATES = {'commission_rate', 'payment_rate', 'tax_rate', 'ad_rate'}
POSITIVE = {'pack_quantity', 'fx_rub_per_cny', 'weight_kg', 'length_cm', 'width_cm',
            'height_cm', 'volumetric_divisor', 'max_billable_kg', 'max_delivery_days',
            'test_units', 'loss_cap'}
COUNTS = {'pack_quantity', 'review_count', 'sales_actual', 'test_units'}
GATES = {'account_eligible', 'compliance_verified', 'logistics_verified'}
UNITS = {**{k: 'money' for k in MONEY}, **{k: 'ratio' for k in RATES},
         **{k: 'boolean' for k in GATES}, **{k: 'count' for k in COUNTS},
         'sales_estimate': 'count', 'rating': 'score', 'fx_rub_per_cny': 'RUB/CNY',
         'weight_kg': 'kg', 'max_billable_kg': 'kg', 'length_cm': 'cm', 'width_cm': 'cm',
         'height_cm': 'cm', 'volumetric_divisor': 'cm3/kg', 'delivery_days': 'days',
         'max_delivery_days': 'days', 'stock_days': 'days', 'revenue_basis': 'text',
         'review_on': 'text', 'stop_condition': 'text', 'brand': 'text'}
NUMERIC = MONEY | RATES | POSITIVE | COUNTS | {'rating', 'sales_estimate', 'delivery_days', 'stock_days'}


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def strict_load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError('nonfinite JSON number: ' + value)

    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=bad_constant)


def check(document, as_of, required=(), max_age_days=7, source_root=None):
    """Validate evidence; requested fields apply to candidate records only."""
    errors, missing = [], {}
    if not isinstance(as_of, date) or type(max_age_days) is not int or max_age_days < 0:
        return {'status': 'HOLD', 'errors': ['invalid_audit_policy'], 'missing_fields': {}}
    validator = Draft202012Validator(strict_load(SCHEMA), format_checker=FormatChecker())
    shape_errors = sorted(validator.iter_errors(document), key=lambda e: str(list(e.path)))
    if shape_errors:
        return {'status': 'HOLD', 'errors': ['schema:' + '/'.join(map(str, e.path)) + ':' + e.message
                                           for e in shape_errors], 'missing_fields': {}}
    sources = {}
    for source in document['sources']:
        sid = source['id']
        if sid in sources:
            errors.append('duplicate_source:' + sid)
        sources[sid] = source
        try:
            zone = ZoneInfo(source['timezone'])
            captured = datetime.fromisoformat(source['captured_at'].replace('Z', '+00:00'))
            start, end = date.fromisoformat(source['period_start']), date.fromisoformat(source['period_end'])
            captured_day = captured.astimezone(zone).date()
            if captured.utcoffset() is None or not start <= end <= captured_day <= as_of:
                errors.append('invalid_source_time:' + sid)
            if (as_of - captured_day).days > max_age_days or (as_of - end).days > max_age_days:
                errors.append('stale_source:' + sid)
        except (ValueError, ZoneInfoNotFoundError, OverflowError):
            errors.append('invalid_source_time:' + sid)
        coverage = source['coverage']
        if coverage['total'] is not None and coverage['selected'] > coverage['total']:
            errors.append('invalid_coverage:' + sid)
        if source['scope'] == 'declared_market' and (
                coverage['total'] is None or coverage['selected'] != coverage['total']
                or not coverage['pagination_complete']):
            errors.append('incomplete_market_scope:' + sid)
        if not document['synthetic'] and (source['scope'] == 'scenario' or source['module'] == 'scenario'):
            errors.append('scenario_source_in_live_data:' + sid)
        if source_root is not None:
            root = Path(source_root).resolve()
            target = (root / source['locator']).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                errors.append('raw_file_unavailable:' + sid)
            elif hashlib.sha256(target.read_bytes()).hexdigest() != source['raw_sha256']:
                errors.append('raw_hash_mismatch:' + sid)
    ids = set()
    for record in document['records']:
        rid = record['record_id']
        if rid in ids:
            errors.append('duplicate_record:' + rid)
        ids.add(rid)
        missing[rid] = []
        if record['role'] == 'candidate':
            missing[rid] = [name for name in required if name not in record['fields']
                            or record['fields'][name]['kind'] == 'UNKNOWN']
        for name, field in record['fields'].items():
            at = rid + ':' + name
            value = field['value']
            if type(value) in (int, float) and not finite_number(value):
                errors.append('invalid_number:' + at)
                continue
            if field['kind'] == 'UNKNOWN':
                if any(sid not in sources for sid in field['source_ids']):
                    errors.append('unknown_source:' + at)
                continue
            linked = [sources[sid] for sid in field['source_ids'] if sid in sources]
            if len(linked) != len(field['source_ids']):
                errors.append('unknown_source:' + at)
            if any(name not in source['field_map'] for source in linked):
                errors.append('missing_field_mapping:' + at)
            if name in UNITS and field['unit'] != UNITS[name]:
                errors.append('wrong_unit:' + at)
            if name in NUMERIC and (not finite_number(value) or value < 0):
                errors.append('invalid_number:' + at)
                continue
            if name in COUNTS and (type(value) is not int):
                errors.append('invalid_count:' + at)
            if name in POSITIVE and value <= 0:
                errors.append('nonpositive:' + at)
            if name in RATES and value >= 1:
                errors.append('invalid_rate:' + at)
            if name == 'rating' and value > 5:
                errors.append('invalid_rating:' + at)
            if name in GATES and type(value) is not bool:
                errors.append('invalid_gate:' + at)
            if name in MONEY:
                expected_currency = 'CNY' if name in CNY else 'RUB'
                if any(source['currency'] is None for source in linked):
                    errors.append('unknown_source_currency:' + at)
                if any(source['currency'] != expected_currency for source in linked) and 'conversion:' not in field['reason']:
                    errors.append('missing_currency_conversion:' + at)
                if field['currency'] != expected_currency:
                    errors.append('wrong_currency:' + at)
                # Currency conversion must already be documented in the mapped value.
                if any(source['money_unit'] not in ('major', 'minor') for source in linked):
                    errors.append('unknown_money_unit:' + at)
                if any(source['money_unit'] == 'minor' for source in linked) and 'conversion:' not in field['reason']:
                    errors.append('missing_unit_conversion:' + at)
            elif field['currency'] is not None:
                errors.append('unexpected_currency:' + at)
            if name in ('sales_actual', 'revenue_actual') and (
                    field['kind'] != 'FACT' or any(source['module'] != 'own' for source in linked)):
                errors.append('unverified_actual:' + at)
            if name in ('sales_estimate', 'revenue_estimate') and field['kind'] != 'ESTIMATE':
                errors.append('estimate_promoted_to_fact:' + at)
            if name in ('sales_estimate', 'revenue_estimate') and any(
                    source['provider'] == 'ozon_storefront' for source in linked):
                errors.append('proxy_as_sales:' + at)
            if not document['synthetic'] and field['kind'] == 'FACT' and any(
                    source['module'] == 'scenario' for source in linked):
                errors.append('scenario_as_fact:' + at)
    if required and not any(r['role'] == 'candidate' for r in document['records']):
        errors.append('missing_candidate')
    for conflict in document['conflicts']:
        if (conflict['record_id'] not in ids or any(s not in sources for s in conflict['source_ids'])
                or len(set(conflict['source_ids'])) < 2):
            errors.append('invalid_conflict_reference')
        if not conflict['resolution']:
            errors.append('unresolved_conflict:' + conflict['record_id'] + ':' + conflict['field'])
    blocked = bool(errors or any(missing.values()))
    return {'schema_version': document['schema_version'], 'dataset_id': document['dataset_id'],
            'synthetic': document['synthetic'], 'as_of': as_of.isoformat(),
            'status': 'HOLD' if blocked else ('VALID_SYNTHETIC' if document['synthetic'] else 'READY_FOR_REVIEW'),
            'errors': sorted(set(errors)), 'missing_fields': missing,
            'unknown_fields': {r['record_id']: [k for k, f in r['fields'].items() if f['kind'] == 'UNKNOWN']
                               for r in document['records']},
            'limitations': ['Structure and declared provenance only; no source authenticity or business GO verified.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--as-of', required=True, type=date.fromisoformat)
    parser.add_argument('--required', nargs='*', default=[])
    parser.add_argument('--max-age-days', type=int, default=7)
    parser.add_argument('--source-root', type=Path)
    args = parser.parse_args()
    try:
        result = check(strict_load(args.input), args.as_of, args.required, args.max_age_days, args.source_root)
    except (ValueError, OSError) as exc:
        result = {'status': 'HOLD', 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if result['status'] == 'HOLD' else 0


if __name__ == '__main__':
    raise SystemExit(main())
