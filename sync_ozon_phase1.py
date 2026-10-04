#!/usr/bin/env python3
"""Maintain independently portable copies of the phase-one contract and runtime."""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
OZON = ROOT / 'sealeap-amazon-skills/ozon'
CANONICAL = OZON / 'sealeap-ozon-data-audit'
PHASE1 = ('mpstats-data-audit', 'niche-screening', 'competitor-map', 'price-segment',
          'unit-economics', 'fulfillment-choice')
REFERENCES = ('data-contract.md', 'schema.json', 'adapters.md', 'mpstats.md')


def pairs():
    for name in PHASE1:
        folder = OZON / ('sealeap-ozon-' + name)
        for reference in REFERENCES:
            yield CANONICAL / 'references' / reference, folder / 'references' / reference
        if name in ('mpstats-data-audit', 'unit-economics'):
            yield CANONICAL / 'scripts/audit.py', folder / 'scripts/audit.py'
            yield CANONICAL / 'requirements.txt', folder / 'requirements.txt'
        if name == 'unit-economics':
            yield CANONICAL / 'scripts/economics.py', folder / 'scripts/economics.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    mismatches = []
    for source, target in pairs():
        if args.check:
            if not target.is_file() or source.read_bytes() != target.read_bytes():
                mismatches.append(str(target.relative_to(ROOT)))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    if mismatches:
        print('Portable copies differ:\n' + '\n'.join(mismatches))
        return 1
    print('Portable phase-one resources synchronized' if not args.check else 'Portable phase-one resources match')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
