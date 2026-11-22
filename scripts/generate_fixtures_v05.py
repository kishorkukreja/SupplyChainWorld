#!/usr/bin/env python3
"""Regenerate fixtures/dynamic/v0.5/scenarios.json (issue #19 fixes, finding 1: the task defect).

The v0.5 family has exactly the v0.4 numbers and rules. The only change is the scenario id carried INSIDE the
world: v0.4 used descriptive ids such as `s04-warned-delayed-10d`, which named the outcome class. Here each
scenario id is an opaque label, `scn-` plus 8 hex characters of a SHA-256 hash of the scenario's visible-side
parameters (every field except the id and the hidden outcome fields `delay_outcome` and `delayed_arrival_day`).
Two scenarios that differ only in the hidden outcome therefore share one label. The fixture id (outside the world,
a file key for humans and for the test harness) is renamed s04- to s05- and still says what the scenario is.

This script imports NOTHING from `supplychainworld`. Its only input is the plain-data v0.4 fixture file.

Usage: python scripts/generate_fixtures_v05.py [--check]
  --check  exit nonzero if the committed scenarios.json differs from this script's output.
All numbers are PROVISIONAL, needs practitioner value. Not reviewed by a practitioner.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'fixtures/dynamic/v0.4/scenarios.json'
OUT = ROOT / 'fixtures/dynamic/v0.5/scenarios.json'
EXCLUDED = ('scenario_id', 'delay_outcome', 'delayed_arrival_day', 'schema_version', 'runtime_version')


def label(scenario):
    visible = {k: v for k, v in scenario.items() if k not in EXCLUDED}
    blob = json.dumps(visible, sort_keys=True, separators=(',', ':'))
    return 'scn-' + hashlib.sha256(blob.encode()).hexdigest()[:8]


def build():
    src = json.loads(SOURCE.read_text())
    fixtures = []
    for fx in src['fixtures']:
        scenario = dict(fx['scenario'])
        scenario['scenario_id'] = label(scenario)
        fixtures.append({'fixture_id': fx['fixture_id'].replace('s04-', 's05-', 1), 'horizon_days': fx['horizon_days'],
                         'disruption_class': fx['disruption_class'], 'scenario': scenario})
    basis = ('Synthetic S01 v0.5 family fixtures (issue #19 fixes, finding 1). Same numbers and rules as v0.4 '
             '(fixtures/dynamic/v0.4); only the scenario id inside the world changed, from a descriptive name that gave '
             'away the outcome class to an opaque label derived from the visible parameters '
             '(scripts/generate_fixtures_v05.py). EVERY number is PROVISIONAL, needs practitioner value. Not reviewed by '
             'a practitioner. Penalty rate for percent_of_value is in basis points (150 = 1.5% per day). '
             'Alternate-supplier unit cost is the premium over the primary unit cost only; the base purchase cost of a '
             'recovery lot is cost-neutral and alternate-bought surplus earns no salvage (unresolved assumption, see '
             'docs/acceptance/dynamic-v0.4-provisional-values.md).')
    return {'basis': basis, 'fixtures': fixtures}


def main():
    text = json.dumps(build(), indent=1) + '\n'
    if '--check' in sys.argv:
        if not OUT.exists() or OUT.read_text() != text:
            print('scenarios.json differs from the generator output', file=sys.stderr)
            return 1
        print('scenarios.json matches the generator output')
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f'wrote {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
