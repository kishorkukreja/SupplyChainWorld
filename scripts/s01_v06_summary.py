#!/usr/bin/env python3
"""The S01 audit's mutation and fuzz campaign run against v0.5 (before) and v0.6 (after).

It reuses `scripts/s01_audit_summary.py` unchanged (same seeds, same mutation operators, same fuzz generators, same
counting rules) and only changes which versions are measured. For v0.6 it also counts how many garbage histories were
rejected by the checker's last-resort guard (`unreadable_guard`) instead of by an ordinary check, so a zero crash
count cannot hide behind a blanket exception handler.

Writes evidence/s01-v06/mutation-fuzz-summary.md and .json. Deterministic (seeded; Hypothesis derandomized). No clock,
network or model call.

Usage: PYTHONPATH=src python scripts/s01_v06_summary.py [--out evidence/s01-v06] [--no-write]
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'scripts'))

spec = importlib.util.spec_from_file_location('s01_audit_summary', ROOT / 'scripts/s01_audit_summary.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

import support  # noqa: E402,F401
from support.s01_v6 import V5, V6  # noqa: E402

GUARD = {'trips': 0, 'calls': 0}
_orig = V6._verify


def _counting_verify(*a, **kw):
    report = _orig(*a, **kw)
    GUARD['calls'] += 1
    GUARD['trips'] += bool(getattr(report, 'metrics', {}).get('unreadable_guard'))
    return report


def run():
    audit.VERSIONS = {'v0.5': V5, 'v0.6': V6}
    mutation = audit.mutation_campaign()
    V6._verify = _counting_verify
    GUARD.update(trips=0, calls=0)
    try:
        fuzz = audit.fuzz_campaign()
    finally:
        V6._verify = _orig
    return mutation, fuzz, dict(GUARD)


def markdown(mutation, fuzz, guard):
    a, b = mutation['v0.5'], mutation['v0.6']
    fa, fb = fuzz['v0.5'], fuzz['v0.6']
    lines = [
        '# S01 v0.6: mutation and fuzz summary, before (v0.5 checker) and after (v0.6 checker)', '',
        'Nothing here is practitioner-reviewed and nothing claims model ability. These are software tests of synthetic rules.',
        'Same campaign as `evidence/s01-audit/mutation-fuzz-summary.md` (same seeds, operators, generators and counting rules,',
        'run by `scripts/s01_v06_summary.py` through `scripts/s01_audit_summary.py`). Deterministic. Regenerate:',
        '`PYTHONPATH=src python scripts/s01_v06_summary.py`.', '',
        '## Before and after in plain numbers', '',
        '| measure | v0.5 checker (before) | v0.6 checker (after) |', '|---|---|---|',
        f"| tampered recorded histories tried | {a['history_mutants']} | {b['history_mutants']} |",
        f"| rejected by the checker | {a['history_killed']} | {b['history_killed']} |",
        f"| accepted although tampered (survived) | {a['history_mutants'] - a['history_killed']} | {b['history_mutants'] - b['history_killed']} |",
        f"| checker crashes on tampered histories | {a.get('verifier_crashes', 0)} | {b.get('verifier_crashes', 0)} |",
        f"| forged scorecards rejected | {a['scorecard_killed']} of {a['scorecard_mutants']} | {b['scorecard_killed']} of {b['scorecard_mutants']} |",
        f"| forged action logs rejected | {a['action_log_killed']} of {a['action_log_mutants']} | {b['action_log_killed']} of {b['action_log_mutants']} |",
        f"| garbage histories fed to the checker | {fa.get('garbage_histories', 0)} | {fb.get('garbage_histories', 0)} |",
        f"| checker crashes on garbage histories | {fa.get('verifier_history_crashes', 0)} | {fb.get('verifier_history_crashes', 0)} |",
        f"| garbage accepted as complete and feasible | {fa.get('garbage_histories_accepted_as_complete_feasible', 0)} | {fb.get('garbage_histories_accepted_as_complete_feasible', 0)} |",
        f"| damaged scenarios that crash the checker (instead of the documented ScenarioError) | {fa.get('verifier_scenario_crashes', 0)} | {fb.get('verifier_scenario_crashes', 0)} |",
        f"| malformed tool calls refused with state unchanged | {fa.get('tool_calls_rejected', 0)} of {fa.get('malformed_tool_calls', 0)} (changed: {fa.get('tool_calls_state_changed', 0)}) | {fb.get('tool_calls_rejected', 0)} of {fb.get('malformed_tool_calls', 0)} (changed: {fb.get('tool_calls_state_changed', 0)}) |",
        '',
        f"Same campaign, small difference in the v0.5 garbage-crash count (311 here, 321 in the audit summary): Hypothesis derandomizes from the test function, so the generated garbage differs slightly between the two scripts; the counting rules are identical. Honesty note on the crash count. The v0.6 checker has a last-resort guard: if an unexpected error escapes while it reads a "
        f"recorded history it reports the history as malformed instead of crashing. In this campaign that guard fired on "
        f"{guard['trips']} of {guard['calls']} v0.6 checker calls during the fuzz section. Those were rejections, never a "
        f"feasible verdict; a nonzero number means some garbage shape is rejected by the guard and not by a named check.", '',
        '## Result against the requirement', '',
        f"* Every v0.6 history mutant rejected: {'YES' if b['history_killed'] == b['history_mutants'] else 'NO'} "
        f"({b['history_killed']} of {b['history_mutants']}).",
        f"* Zero checker crashes: {'YES' if not b.get('verifier_crashes', 0) and not fb.get('verifier_history_crashes', 0) and not fb.get('verifier_scenario_crashes', 0) else 'NO'}.", '']
    for tag, r in mutation.items():
        if r['survivors']:
            lines.append(f'Survivors {tag}: ' + '; '.join(f'{k} x{c}' for k, c in r['survivors'].items()))
    lines += ['', '## History mutation detail (committed fixtures x declared policies)', '',
              'A mutant is counted only if it changes what the record means (see tests/support/mutations.py).', '',
              '| version | episodes | mutants | killed | survived | neutral (not counted) | verifier crashes |', '|---|---|---|---|---|---|---|']
    for tag, r in mutation.items():
        lines.append(f"| {tag} | {r['episodes']} | {r['history_mutants']} | {r['history_killed']} | "
                     f"{r['history_mutants'] - r['history_killed']} | {r['neutral_not_counted']} | {r.get('verifier_crashes', 0)} |")
    lines += ['', '## Fuzz detail (1000 generated inputs per row, Hypothesis, derandomize)', '',
              '| version | malformed tool calls | rejected | state changed | crashes | damaged scenarios | refused cleanly by simulator | accepted by simulator | scenario crashes | verifier scenario crashes | garbage histories | verifier history crashes | garbage accepted as complete+feasible |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for tag, r in fuzz.items():
        lines.append(f"| {tag} | {r.get('malformed_tool_calls', 0)} | {r.get('tool_calls_rejected', 0)} | {r.get('tool_calls_state_changed', 0)} | "
                     f"{r.get('tool_call_crashes', 0)} | {r.get('damaged_scenarios', 0)} | {r.get('scenarios_refused_cleanly', 0)} | "
                     f"{r.get('scenarios_accepted_by_simulator', 0)} | {r.get('scenario_crashes', 0)} | {r.get('verifier_scenario_crashes', 0)} | "
                     f"{r.get('garbage_histories', 0)} | {r.get('verifier_history_crashes', 0)} | "
                     f"{r.get('garbage_histories_accepted_as_complete_feasible', 0)} |")
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='evidence/s01-v06')
    ap.add_argument('--no-write', action='store_true')
    args = ap.parse_args()
    mutation, fuzz, guard = run()
    text = markdown(mutation, fuzz, guard)
    if args.no_write:
        print(text)
        return
    out = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / 'mutation-fuzz-summary.json').write_text(
        json.dumps({'mutation': mutation, 'fuzz': fuzz, 'guard': guard}, indent=1, sort_keys=True) + '\n')
    (out / 'mutation-fuzz-summary.md').write_text(text)
    print(text)


if __name__ == '__main__':
    main()
