"""Write observable runner transcripts for the S01 fixtures (issue #24 evidence)."""
import json
from pathlib import Path

from supplychainworld.agent_runner import ObservableRunner, replay, scripted_policy
from supplychainworld.dynamic import OperationalWorld, SupplierDelayScenario

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / 'fixtures/dynamic/supplier-delay-inputs.json').read_text())['fixtures']


def main():
    out = {}
    for f in FIXTURES:
        def factory(f=f):
            return OperationalWorld(f['horizon_days'], scenario=SupplierDelayScenario(**f['scenario']))
        out[f['fixture_id']] = {}
        for policy in ('maintain', 'expedite', 'alternate'):
            t = ObservableRunner(factory()).run(scripted_policy(policy))
            ok, diffs = replay(t, factory)
            out[f['fixture_id']][policy] = {'replay_reproduced': ok, 'replay_differences': diffs, 'transcript': t}
    probes = iter([{'tool': 'read_scenario'}, {'tool': 'release_production', 'arguments': {'quantity': 9}},
                   {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}},
                   {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate'}},
                   {'tool': 'release_production', 'arguments': {'quantity': 4}},
                   {'tool': 'advance_day'}])
    t = ObservableRunner(OperationalWorld()).run(lambda v: next(probes, None))
    out['rejection-demo'] = {'transcript': t, 'replay_reproduced': replay(t, OperationalWorld)[0]}
    (ROOT / 'evidence/issue-24-traces.json').write_text(json.dumps(out, indent=1) + '\n')
    for fid, runs in out.items():
        items = [('probes', runs)] if fid == 'rejection-demo' else list(runs.items())
        for name, r in items:
            tr = r['transcript']
            print(fid, name, tr['status'], 'attempts', len(tr['attempts']), 'cost',
                  (tr['scorecard'] or {}).get('comparison_cost'), 'replay', r['replay_reproduced'])


if __name__ == '__main__':
    main()
