#!/usr/bin/env python3
"""Seeded mutation and fuzz campaign over the S01 verifiers, runners and scenario validators (v0.1 to v0.4).

Writes evidence/s01-audit/mutation-fuzz-summary.json and .md. Deterministic: every random choice comes from a
seeded `random.Random` or from Hypothesis with derandomize=True. No clock, network or model call.

Usage: PYTHONPATH=src python scripts/s01_audit_summary.py [--out evidence/s01-audit] [--label after-fixes] [--no-write]

Run with PYTHONPATH pointing at an older copy of `src/` to measure the code as it was before the audit fixes
(the test helpers in tests/support only use public modules that exist in both).
"""
import argparse
import collections
import importlib
import json
import random
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))

from hypothesis import HealthCheck, given, settings, strategies as st  # noqa: E402

import support  # noqa: E402,F401
from support import fuzz  # noqa: E402
from support.mutations import mutate_actions, mutate_history, mutate_scorecard, semantic_key  # noqa: E402
from support.s01_versions import VERSIONS, fixture_scenario, scripted_transcript  # noqa: E402

MUTANTS_PER_EPISODE = 200
EXPECTED = (ValueError, KeyError, TypeError, StopIteration)


def rejected(v, scenario, history, horizon, **kw):
    try:
        return bool(v.verify(scenario, history, horizon, **kw).violations), None
    except ValueError:
        return True, None
    except Exception as exc:  # noqa: BLE001 - a crash is counted separately
        return True, type(exc).__name__


def mutation_campaign():
    out = {}
    for tag, v in VERSIONS.items():
        row = collections.Counter()
        by_op = collections.defaultdict(collections.Counter)
        survivors = collections.Counter()
        for f in v.fixtures():
            scenario, horizon = fixture_scenario(v, f)
            for policy in v.policies:
                transcript, runner = scripted_transcript(v, scenario, horizon, policy)
                world = runner._world
                history, card, sd = world.history(), world.scorecard(), v.scenario_dict(world)
                actions = v.actions(transcript)
                rnd = random.Random(f'{tag}/{f["fixture_id"]}/{policy}')
                row['episodes'] += 1
                for _ in range(MUTANTS_PER_EPISODE):
                    mutant, desc = mutate_history(history, rnd)
                    if mutant is None:
                        continue
                    if semantic_key(mutant) == semantic_key(history):
                        row['neutral_not_counted'] += 1
                        continue
                    row['history_mutants'] += 1
                    bad, crash = rejected(v, sd, mutant, horizon, scorecard=card)
                    by_op[desc['op']]['mutants'] += 1
                    if crash:
                        row['verifier_crashes'] += 1
                    if bad:
                        row['history_killed'] += 1
                        by_op[desc['op']]['killed'] += 1
                    else:
                        survivors[f"{desc['op']} on {desc['event']}"] += 1
                for _ in range(20):
                    lie, _d = mutate_scorecard(card, rnd)
                    if lie is not None:
                        row['scorecard_mutants'] += 1
                        row['scorecard_killed'] += rejected(v, sd, history, horizon, scorecard=lie)[0]
                    bad_actions, _d = mutate_actions(actions, rnd)
                    if bad_actions is not None and json.dumps([a for a in bad_actions if (a.get('result') or {}).get('accepted') is True], sort_keys=True) \
                            != json.dumps([a for a in actions if (a.get('result') or {}).get('accepted') is True], sort_keys=True):
                        row['action_log_mutants'] += 1
                        row['action_log_killed'] += rejected(v, sd, history, horizon, scorecard=card, actions=bad_actions)[0]
        out[tag] = {**row, 'survivors': dict(survivors.most_common(12)),
                    'by_operation': {k: dict(c) for k, c in sorted(by_op.items())}}
    return out


def fuzz_campaign():
    out = {}
    cfg = dict(deadline=None, database=None, derandomize=True, suppress_health_check=list(HealthCheck))
    for tag, v in VERSIONS.items():
        base, horizon = fixture_scenario(v, v.fixtures()[1])
        row = collections.Counter()

        @settings(max_examples=1000, **cfg)
        @given(fuzz.malformed_tool_calls())
        def calls(call):
            runner = v.runner(base, horizon)
            before = runner._world.snapshot()
            try:
                rec = runner.attempt(call)
            except Exception:  # noqa: BLE001
                row['tool_call_crashes'] += 1
                return
            row['malformed_tool_calls'] += 1
            row['tool_calls_rejected'] += not rec['accepted']
            row['tool_calls_state_changed'] += runner._world.snapshot() != before
        calls()

        import test_s01_versions_fuzz as tf   # reuse the exact strategies the tests use

        @settings(max_examples=1000, **cfg)
        @given(tf.damaged_scenarios(base), st.one_of(st.just(horizon), tf.junk))
        def scenarios(sc, h):
            row['damaged_scenarios'] += 1
            try:
                v.world(sc, h)
                row['scenarios_accepted_by_simulator'] += 1
            except EXPECTED:
                row['scenarios_refused_cleanly'] += 1
            except Exception:  # noqa: BLE001
                row['scenario_crashes'] += 1
            try:
                v.verify(sc, [], horizon)
            except ValueError:
                row['scenarios_refused_by_verifier'] += 1
            except Exception:  # noqa: BLE001
                row['verifier_scenario_crashes'] += 1
        scenarios()

        scenario2, horizon2 = fixture_scenario(v, v.fixtures()[1])
        _, runner = scripted_transcript(v, scenario2, horizon2, v.policies[-1])
        sd = v.scenario_dict(runner._world)
        card = runner._world.scorecard()

        @settings(max_examples=1000, **cfg)
        @given(st.lists(st.one_of(fuzz.json_blobs, st.fixed_dictionaries({}, optional={
            'day': tf.junk, 'kind': st.sampled_from(['receipt', 'notice', 'signal', 'recovery', 'release', 'day_close',
                                                     'close_day', 'episode_complete', 'day_open']),
            'details': tf.junk, 'accepted': tf.junk, 'state': tf.junk})), max_size=10),
               st.one_of(st.none(), st.lists(fuzz.json_blobs, max_size=4)))
        def histories(hist, actions):
            row['garbage_histories'] += 1
            try:
                rep = v.verify(sd, hist, horizon2, scorecard=card, actions=actions)
                row['garbage_histories_reported'] += 1
                row['garbage_histories_accepted_as_complete_feasible'] += bool(rep.feasible and rep.complete)
            except ValueError:
                row['garbage_histories_refused'] += 1
            except Exception:  # noqa: BLE001
                row['verifier_history_crashes'] += 1
        histories()
        out[tag] = dict(row)
    return out


def example_budget():
    """Hypothesis examples requested by the S01 audit property and fuzz tests (ci profile)."""
    import unittest
    total, per_module = 0, {}
    loader = unittest.TestLoader()
    for path in sorted((ROOT / 'tests').glob('test_s01_*_property.py')) + sorted((ROOT / 'tests').glob('test_s01_*_fuzz.py')):
        mod = importlib.import_module(path.stem)

        def flat(s):
            for t in s:
                yield from flat(t) if isinstance(t, unittest.TestSuite) else [t]
        n = tests = 0
        for t in flat(loader.loadTestsFromModule(mod)):
            fn = getattr(t, t._testMethodName)
            s = getattr(fn, '_hypothesis_internal_use_settings', None)
            if getattr(fn, 'is_hypothesis_test', False) and s is not None:
                n += s.max_examples
                tests += 1
        per_module[path.stem] = {'hypothesis_tests': tests, 'examples_requested': n}
        total += n
    return {'total_examples_requested': total, 'per_module': per_module}


def markdown(report):
    m, f, b = report['mutation'], report['fuzz'], report['hypothesis_budget']
    lines = [f"# S01 audit: mutation and fuzz summary ({report['label']})", '',
             'Seeded and deterministic. Regenerate: `PYTHONPATH=src python scripts/s01_audit_summary.py`.', '',
             '## History mutation (committed fixtures x declared policies, independent verifier)', '',
             'A mutant is counted only if it changes what the record means; accepted zero-unit releases, rejected-command',
             'records and unknown record kinds are "neutral" (see tests/support/mutations.py). Killed = verifier reports a violation.', '',
             '| version | episodes | mutants | killed | survived | neutral (not counted) | verifier crashes | scorecard forgeries killed | action-log forgeries killed |',
             '|---|---|---|---|---|---|---|---|---|']
    for tag, r in m.items():
        lines.append(f"| {tag} | {r['episodes']} | {r['history_mutants']} | {r['history_killed']} | {r['history_mutants'] - r['history_killed']} | "
                     f"{r['neutral_not_counted']} | {r.get('verifier_crashes', 0)} | {r['scorecard_killed']}/{r['scorecard_mutants']} | "
                     f"{r['action_log_killed']}/{r['action_log_mutants']} |")
    for tag, r in m.items():
        if r['survivors']:
            lines += ['', f'Survivors {tag}: ' + '; '.join(f'{k} x{c}' for k, c in r['survivors'].items())]
    lines += ['', '## Fuzz campaign (1000 generated inputs per row and version, Hypothesis, derandomize)', '',
              '| version | malformed tool calls | rejected | state changed | crashes | damaged scenarios | refused cleanly by simulator | accepted by simulator | scenario crashes | verifier scenario crashes | garbage histories | verifier history crashes | garbage accepted as complete+feasible |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for tag, r in f.items():
        lines.append(f"| {tag} | {r.get('malformed_tool_calls', 0)} | {r.get('tool_calls_rejected', 0)} | {r.get('tool_calls_state_changed', 0)} | "
                     f"{r.get('tool_call_crashes', 0)} | {r.get('damaged_scenarios', 0)} | {r.get('scenarios_refused_cleanly', 0)} | "
                     f"{r.get('scenarios_accepted_by_simulator', 0)} | {r.get('scenario_crashes', 0)} | {r.get('verifier_scenario_crashes', 0)} | "
                     f"{r.get('garbage_histories', 0)} | {r.get('verifier_history_crashes', 0)} | "
                     f"{r.get('garbage_histories_accepted_as_complete_feasible', 0)} |")
    lines += ['', '## Hypothesis example budget of the audit tests (ci profile)', '',
              f"Total examples requested per run: {b['total_examples_requested']}.", '',
              '| module | Hypothesis tests | examples requested |', '|---|---|---|']
    lines += [f"| {k} | {x['hypothesis_tests']} | {x['examples_requested']} |" for k, x in b['per_module'].items()]
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='evidence/s01-audit')
    ap.add_argument('--label', default='after fixes')
    ap.add_argument('--no-write', action='store_true')
    ap.add_argument('--skip-budget', action='store_true')
    args = ap.parse_args()
    report = {'label': args.label, 'mutation': mutation_campaign(), 'fuzz': fuzz_campaign(),
              'hypothesis_budget': {'total_examples_requested': None, 'per_module': {}} if args.skip_budget else example_budget()}
    text = markdown(report)
    if args.no_write:
        print(text)
        return
    out = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / 'mutation-fuzz-summary.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    (out / 'mutation-fuzz-summary.md').write_text(text)
    print(text)


if __name__ == '__main__':
    main()
