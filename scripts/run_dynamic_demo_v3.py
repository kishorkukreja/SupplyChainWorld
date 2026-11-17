#!/usr/bin/env python3
"""Run the S01 v0.3 family demonstration (issue #36, round 2) and write the evidence packet.

Usage: PYTHONPATH=src python scripts/run_dynamic_demo_v3.py [--out evidence/issue-36-v03]
Deterministic: no clock, randomness, network or model calls enter the packet.
"""
import argparse
import csv
import html
import json
from pathlib import Path

from supplychainworld.agent_runner_v3 import POLICIES_V3
from supplychainworld.dynamic_demo_v3 import EXPERIENCE_FIXTURE, EXPERIENCE_POLICY, METRICS, build_packet

ROOT = Path(__file__).resolve().parents[1]
REPLAY_CMD = 'PYTHONPATH=src python scripts/run_dynamic_demo_v3.py --out evidence/issue-36-v03'
BANNER = 'ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies, synthetic scenarios, no LLM, reviewed: no, not independent (owner-practitioner round 2 changes applied).'


def dumps(obj):
    return json.dumps(obj, indent=1) + '\n'


def fmt_event(e):
    d = ', '.join(f'{k}={v}' for k, v in e['details'].items())
    flag = '' if e['accepted'] else f" REJECTED ({e['reason']})"
    return f"day {e['day']} {e['kind']}{(' ' + d) if d else ''}{flag}"


def timeline_text(packet):
    lines = ['S01 v0.3 timeline. ' + BANNER, '']
    for fid, runs in packet['episodes'].items():
        for policy, ep in runs.items():
            t = ep['transcript']
            lines += [f"=== {fid} / {policy} (horizon {t['horizon_days']} days, status {t['status']}) ===", 'initial events:']
            lines += ['  ' + fmt_event(e) for e in t['initial']['events']]
            for a in t['attempts']:
                args = ','.join(f'{k}={v}' for k, v in a['arguments'].items())
                verdict = 'accepted' if a['accepted'] else f"REJECTED ({a['reason']})"
                lines.append(f"#{a['seq']:02d} day {a['day']} agent calls {a['tool']}({args}) -> {verdict}")
                lines += ['      ' + fmt_event(e) for e in a['events']]
            lines += [f"final scorecard: {json.dumps(t['scorecard'])}", '']
    return '\n'.join(lines)


def ledger_rows(packet):
    rows = []
    for fid, runs in packet['episodes'].items():
        for policy, ep in runs.items():
            for r in ep['report'].ledger:
                rows.append({'fixture': fid, 'policy': policy, **r})
    return rows


def flat_scorecard_rows(packet):
    rows = []
    for fid, runs in packet['episodes'].items():
        for p in POLICIES_V3:
            ep = runs[p]
            row = {'fixture': fid, 'policy': p}
            for m, (path, _, _) in METRICS.items():
                v = ep['scorecard']
                for k in path:
                    v = v[k]
                row[m] = v
            row.update(salvage_credit=ep['scorecard']['cost']['salvage_credit'],
                       cancelled_units=ep['scorecard']['service']['cancelled_units'],
                       verifier_feasible=ep['report'].feasible, matches_hand_ledger=all(ep['hand'].values()),
                       replay_reproduced=ep['replay']['transcript_reproduced'])
            rows.append(row)
    return rows


def md_table(rows):
    cols = list(rows[0])
    return '\n'.join(['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)] +
                     ['| ' + ' | '.join(str(r[c]) for c in cols) + ' |' for r in rows])


def comparison_md(packet):
    out = ['# Per-metric comparison (no overall winner is declared)', '', BANNER, '',
           'Each table shows one scenario. "Best here" marks the policy (or tie) that is best on that metric alone.',
           'Cost, service, tier impact, downstream impact and supply risk are never combined into one number.', '']
    for fid, c in packet['comparison'].items():
        pols = list(next(iter(c['metrics'].values()))['values'])
        out += [f'## {fid}', '', '| metric | dimension | better | ' + ' | '.join(pols) + ' | best here |',
                '|' + '---|' * (4 + len(pols))]
        for m, row in c['metrics'].items():
            out.append(f"| {m} | {row['dimension']} | {row['better']} | " + ' | '.join(str(row['values'][p]) for p in pols)
                       + ' | ' + ', '.join(row['best_on_this_metric_alone']) + ' |')
        out += ['', f"Best on every metric: {c['best_on_every_metric'] or 'none'}. {c['trade_offs'] or ''}", '']
    return '\n'.join(out)


def checks_json(packet):
    out = {'note': 'Verifier results re-derived from recorded commands; self-reported pass flags are ignored. ' + BANNER,
           'episodes': {}}
    for fid, runs in packet['episodes'].items():
        out['episodes'][fid] = {}
        for p, ep in runs.items():
            r = ep['report']
            out['episodes'][fid][p] = {'feasible': r.feasible, 'complete': r.complete, 'violations': r.violations,
                                       'matches_hand_worked': ep['hand'], 'derived_scorecard': r.scorecard,
                                       'ignored_self_reports': r.ignored_self_reports, 'corruption_cases': ep['tamper']}
    out['rejection_probes'] = packet['probes']
    out['paired_signal_identical_until_firm_notice'] = packet['paired_signal_identical']
    out['leak_scan'] = {'experience_record': packet['experience_leaks'], 'all_episodes': packet['all_episode_leaks']}
    return out


def replay_json(packet):
    return {'command': REPLAY_CMD,
            'method': 'Recorded tool calls re-driven through a fresh ObservableRunnerV3 and world; views, outcomes, state changes, final state and scorecard must match exactly. The replayed history is also compared and re-verified.',
            'episodes': {fid: {p: {**ep['replay'], 'attempts': len(ep['transcript']['attempts'])} for p, ep in runs.items()}
                         for fid, runs in packet['episodes'].items()}}


def experience_md(rec):
    lines = [f"# Observable experience record: {rec['scenario_id']} ({rec['horizon_days']} days)", '',
             f"Agent: {rec['agent']}. Values: {rec['values_status']}.",
             'Shows only what the agent saw, the call it made, the outcome and the resulting events. No answer key, other policy or verifier output.', '']
    for s in rec['steps']:
        o = s['observation']
        st = o['state']
        lines.append(f"- step {s['seq']}, day {s['day']}: components={st['component_on_hand']}, finished={st['finished_on_hand']}, "
                     f"delivered={st['delivered_total']}, signals={[x['level'] for x in st['signals']]}, "
                     f"notices={[n['text'] for n in st['notices']]}; called `{s['action']['tool']}` {s['action']['arguments']} -> "
                     f"{'accepted' if s['outcome']['accepted'] else 'rejected: ' + str(s['outcome']['reason'])}")
    lines += ['', f"Final scorecard: {json.dumps(rec['final_scorecard'])}"]
    return '\n'.join(lines) + '\n'


GATE_TITLES = {'G1': 'Coherent initial world', 'G2': 'Actual time progression', 'G3': 'Executed disruption, signal and recovery',
               'G4': 'Consequential state changes (hand ledgers)', 'G5': 'Per-metric scorecards (hand metrics)',
               'G6': 'Independent checking', 'G7': 'Failure behavior', 'G8': 'Replay and no-leak', 'G9': 'Honest demonstration'}


def gate_report(packet):
    rows = []
    for k, title in GATE_TITLES.items():
        v = packet['gates'][k]
        status = 'Evidence produced, unreviewed' if v['pass'] else ('Partial: labels stated; practitioner re-review pending' if v['pass'] is None else 'FAILED')
        rows.append(f"| {k} {title} | {status} | {v['evidence']} |")
    return '\n'.join([
        '# Issue #36 gate report (S01 v0.3 family)', '', BANNER, '',
        'Regenerate: `' + REPLAY_CMD + '`. Output is deterministic.', '',
        '| Gate | Status | Evidence |', '|---|---|---|', *rows, '',
        'Implemented: yes. Tested: yes (automated, synthetic fixtures). Practitioner-reviewed: no; the repair awaits re-review.', '',
        'No model-ability claim. No overall best policy is declared. The warned scenarios use an authored hint value that is not calibrated.', ''])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='evidence/issue-36-v03')
    args = ap.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    packet = build_packet()
    tl = timeline_text(packet)
    (out / 'timeline.txt').write_text(tl + '\n')
    rows = ledger_rows(packet)
    (out / 'state-ledger.json').write_text(dumps(rows))
    with (out / 'state-ledger.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    sc = flat_scorecard_rows(packet)
    (out / 'scorecard.json').write_text(dumps({'banner': BANNER, 'full_scorecards': {
        fid: {p: ep['scorecard'] for p, ep in runs.items()} for fid, runs in packet['episodes'].items()}, 'flat': sc}))
    (out / 'scorecard.md').write_text('# Per-metric scorecards (scripted baselines, synthetic scenarios)\n\n' + BANNER + '\n\n' + md_table(sc) + '\n')
    (out / 'comparison.json').write_text(dumps(packet['comparison']))
    (out / 'comparison.md').write_text(comparison_md(packet))
    (out / 'checks.json').write_text(dumps(checks_json(packet)))
    rp = replay_json(packet)
    (out / 'replay.json').write_text(dumps(rp))
    log = [f'command: {REPLAY_CMD}']
    for fid, runs in rp['episodes'].items():
        for p, r in runs.items():
            log.append(f"{fid} {p}: attempts={r['attempts']} transcript_reproduced={r['transcript_reproduced']} "
                       f"state_sequence_identical={r['state_sequence_identical']} scorecard_identical={r['replayed_scorecard_identical']}")
    (out / 'replay.log').write_text('\n'.join(log) + '\n')
    (out / 'experience-record.json').write_text(dumps(packet['experience']))
    (out / 'experience-record.md').write_text(experience_md(packet['experience']))
    (out / 'transcripts.json').write_text(dumps({fid: {p: ep['transcript'] for p, ep in runs.items()}
                                                  for fid, runs in packet['episodes'].items()}))
    gate_md = gate_report(packet)
    (out / 'gate-report.md').write_text(gate_md)
    (out / 'report.html').write_text(
        '<!doctype html><html><head><meta charset="utf-8"><title>S01 v0.3 packet</title>'
        '<style>body{font:14px/1.4 sans-serif;margin:24px}pre{background:#f4f4f4;padding:10px;white-space:pre-wrap;font-size:12px}</style></head><body>'
        f'<h1>S01 v0.3 family demonstration packet</h1><p>{html.escape(BANNER)}</p>'
        f'<h2>Comparison</h2><pre>{html.escape(comparison_md(packet))}</pre><h2>Gates</h2><pre>{html.escape(gate_md)}</pre></body></html>\n')
    print(f'wrote {out}; experience {EXPERIENCE_FIXTURE}/{EXPERIENCE_POLICY}; leaks={packet["experience_leaks"]}')
    for k, v in packet['gates'].items():
        print(k, v['pass'])


if __name__ == '__main__':
    main()
