#!/usr/bin/env python3
"""Run synthetic reference policies; no answer key enters the policy."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from supplychainworld.baselines import run_baseline
from supplychainworld.dynamic import OperationalWorld, SupplierDelayScenario


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', default='fixtures/dynamic/supplier-delay-inputs.json')
    parser.add_argument('--output', required=True, help='path to write full public synthetic traces')
    args = parser.parse_args()
    fixtures = json.loads(Path(args.inputs).read_text())['fixtures']
    traces = {}
    for f in fixtures:
        scenario = SupplierDelayScenario(**f['scenario'])
        traces[f['fixture_id']] = {}
        for policy in ('maintain', 'expedite', 'alternate'):
            result = run_baseline(OperationalWorld(f['horizon_days'], scenario=scenario), policy)
            traces[f['fixture_id']][policy] = asdict(result)
    Path(args.output).write_text(json.dumps(traces, indent=2) + '\n')
    print(json.dumps({fixture: {policy: trace['scorecard'] for policy, trace in policies.items()}
                      for fixture, policies in traces.items()}, indent=2))


if __name__ == '__main__':
    main()
