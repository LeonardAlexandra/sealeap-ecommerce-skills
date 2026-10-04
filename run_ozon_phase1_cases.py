#!/usr/bin/env python3
"""Emit deterministic phase-one case observations for the five frozen fixtures."""
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / 'sealeap-amazon-skills/ozon/sealeap-ozon-data-audit'
sys.path.insert(0, str(AUDIT / 'scripts'))
from audit import strict_load, check
from economics import evaluate
from market import descriptive_market


def main():
    cases = AUDIT / 'references/cases'
    manifest = strict_load(cases / 'expected.json')
    results = []
    for expected in manifest['cases']:
        path = cases / (expected['id'] + '.json')
        document = strict_load(path)
        as_of = date.fromisoformat(manifest['as_of'])
        audit = check(document, as_of, source_root=cases)
        economics = evaluate(document, as_of)
        market = descriptive_market(document) if audit['status'] != 'HOLD' else None
        rows = economics['records'] if 'records' in economics else []
        actual = {'id': expected['id'], 'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'audit': economics['audit']['status'], 'decision': economics['decision'],
                  'source_file_errors': [e for e in audit['errors'] if e.startswith('raw_')],
                  'market': market, 'economic_records': rows,
                  'missing_fields': economics['missing_fields'], 'conflicts': economics['conflicts']}
        actual['passed'] = actual['audit'] == expected['audit'] and actual['decision'] == expected['decision'] and not actual['source_file_errors']
        if 'base_contribution' in expected:
            actual['passed'] &= rows[0]['base']['metrics']['contribution_after_ads_rub'] == expected['base_contribution']
            actual['passed'] &= rows[0]['stress']['metrics']['contribution_after_ads_rub'] == expected['stress_contribution']
            actual['passed'] &= rows[0]['route']['billable_kg'] == expected['billable_kg']
        results.append(actual)
    print(json.dumps({'as_of': manifest['as_of'], 'synthetic': True,
                      'boundary': 'Deterministic reference checks and arithmetic; not an independent LLM or live seller trial.',
                      'passed': all(r['passed'] for r in results), 'cases': results}, ensure_ascii=False, indent=2))
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
