#!/usr/bin/env python3
"""Run the S01 supplier-delay demonstration (issue #26) and write the evidence packet.

Usage: PYTHONPATH=src python scripts/run_dynamic_demo.py [--out evidence/issue-26]
Deterministic: no clock, randomness, network or model calls enter the packet.
"""
import argparse
import csv
import html
import json
from pathlib import Path

from supplychainworld.dynamic_demo import (EXPERIENCE_FIXTURE, EXPERIENCE_POLICY, POLICIES, SCORE_KEYS,
                                           build_packet)

ROOT = Path(__file__).resolve().parents[1]
REPLAY_CMD = 'PYTHONPATH=src python scripts/run_dynamic_demo.py --out evidence/issue-26'


def dumps(obj):
    return json.dumps(obj, indent=1, sort_keys=False) + '\n'


def fmt_event(e):
    d = ', '.join(f'{k}={v}' for k, v in e['details'].items())
    flag = '' if e['accepted'] else f" REJECTED ({e['reason']})"
    return f"day {e['day']} {e['kind']}{(' ' + d) if d else ''}{flag}"


def timeline_text(packet):
    lines = ['S01 supplier-delay timeline (scripted baselines, synthetic fixtures, no LLM)', '']
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
            card = t['scorecard']
            lines += [f"final scorecard: {json.dumps(card)}", '']
    return '\n'.join(lines)


def ledger_rows(packet):
    rows = []
    for fid, runs in packet['episodes'].items():
        for policy, ep in runs.items():
            by_day = {}
            for e in ep['history']:
                by_day.setdefault(e['day'], {})[e['kind']] = e['state']
            for r in ep['report'].ledger:
                op, cl = by_day[r['day']]['day_open'], by_day[r['day']]['day_close']
                rows.append({'fixture': fid, 'policy': policy, 'day': r['day'],
                             'opening_components': op['component_on_hand'], 'opening_finished': op['finished_on_hand'],
                             'received': r['received'], 'released_and_produced': r['produced'], 'shipped': r['shipped'],
                             'closing_components': r['components_close'], 'closing_finished': r['finished_close'],
                             'delivered_total': r['delivered_total'], 'undelivered_assessed': r['undelivered_assessed'],
                             'penalty_total': r['penalty_total'], 'spend_total': r['spend_total'],
                             'recovery': cl['recovery'], 'primary_arrival_day_at_close': cl['primary_arrival_day'],
                             'alternate_arrival_day_at_close': cl['alternate_arrival_day']})
    return rows


def scorecard_rows(packet):
    rows = []
    for fid, runs in packet['episodes'].items():
        for p in POLICIES:
            ep = runs[p]
            rows.append({'fixture': fid, 'policy': p, **{k: ep['scorecard'][k] for k in SCORE_KEYS},
                         'verifier_feasible': ep['report'].feasible, 'verifier_comparison_cost': ep['report'].outcome['comparison_cost'],
                         'replay_reproduced': ep['replay']['transcript_reproduced']})
    return rows


def md_table(rows):
    cols = list(rows[0])
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    out += ['| ' + ' | '.join(str(r[c]) for c in cols) + ' |' for r in rows]
    return '\n'.join(out)


def checks_json(packet):
    out = {'note': 'Verifier results re-derived from recorded commands; self-reported pass flags are ignored.', 'episodes': {}}
    for fid, runs in packet['episodes'].items():
        out['episodes'][fid] = {}
        for p, ep in runs.items():
            r = ep['report']
            out['episodes'][fid][p] = {'feasible': r.feasible, 'complete': r.complete, 'violations': r.violations,
                                       'metrics': r.metrics, 'outcome': r.outcome, 'ignored_self_reports': r.ignored_self_reports,
                                       'corruption_cases': ep['tamper']}
    out['rejection_probes'] = packet['probes']
    return out


def replay_json(packet):
    return {'command': REPLAY_CMD,
            'method': 'Recorded tool calls re-driven through a fresh ObservableRunner and world; views, outcomes, state changes, final state and scorecard must match exactly. The replayed world history is also compared and re-verified.',
            'episodes': {fid: {p: {**ep['replay'], 'attempts': len(ep['transcript']['attempts'])} for p, ep in runs.items()}
                         for fid, runs in packet['episodes'].items()}}


def experience_md(rec):
    lines = [f"# Observable experience record: {rec['scenario_id']} ({rec['horizon_days']} days)", '',
             f"Agent: {rec['agent']}.", 'Shows only what the agent saw, the call it made, the outcome and the resulting events. No answer key, other policy or verifier output is included.', '']
    for s in rec['steps']:
        o = s['observation']
        st = o['state']
        lines.append(f"- step {s['seq']}, day {s['day']} ({o['clock']['phase']}): saw components={st['component_on_hand']}, finished={st['finished_on_hand']}, "
                     f"delivered={st['delivered_total']}, notices={st['notices']}; called `{s['action']['tool']}` {s['action']['arguments']} -> "
                     f"{'accepted' if s['outcome']['accepted'] else 'rejected: ' + str(s['outcome']['reason'])}")
    lines += ['', f"Final scorecard: {rec['final_scorecard']}"]
    return '\n'.join(lines) + '\n'


GATE_TITLES = {'G1': 'Coherent initial world', 'G2': 'Actual time progression', 'G3': 'Executed disruption and recovery',
               'G4': 'Consequential state changes', 'G5': 'Baseline differences', 'G6': 'Independent checking',
               'G7': 'Failure behavior', 'G8': 'Replay and data', 'G9': 'Honest demonstration'}
UNRESOLVED = [
    'All fixture quantities, prices, the penalty schedule (assessed at closes on and after the due day), no holding cost, and exclusive recovery choice are unreviewed engineering assumptions. No practitioner has reviewed them.',
    'The 15-day fixture (notice day 6, due day 10, delayed arrival day 12) has hand-worked ledgers but no practitioner-confirmed expected outcome and no table in the acceptance document.',
    'Whether penalizing an undelivered unit at every close from the due day (rather than once, or per elapsed day) reflects real contracts is unresolved.',
    'Whether the alternate supplier should deliver at once, and whether surplus components (8 left at day 5) carry cost, is unresolved.',
    'Premature/extra receipt and over-budget recovery rejection is shown at verifier level, not through agent tools; no hostile-agent sandbox exists (the runner boundary is for well-behaved in-process policies).',
    'Scripted policies read the same visible view an LLM would, but no LLM was run. The demonstration says nothing about model ability.',
]


def gate_report(packet, screenshot):
    g = packet['gates']
    rows = []
    for k in GATE_TITLES:
        v = g[k]
        status = 'Evidence produced, unreviewed' if v['pass'] else ('Partial / cannot be called passed' if v['pass'] is None else 'FAILED')
        if k == 'G7' and v['pass']:
            status = 'Evidence produced (tools) plus unit-test evidence (verifier), unreviewed'
        if k == 'G9' and v['pass'] is None:
            status = 'Partial: labels and limits stated; practitioner review pending'
        rows.append(f"| {k} {GATE_TITLES[k]} | {status} | {v['evidence']} |")
    shot = (f"Screenshot: real headless Chrome capture of the rendered packet at `{screenshot}`." if screenshot
            else 'Screenshots: none produced for this packet; trace, ledger and check files are the evidence.')
    return '\n'.join([
        '# Issue #26 end-to-end gate report (S01 supplier delay, DYN05)', '',
        'Regenerate: `' + REPLAY_CMD + '`. Output is deterministic.', '',
        '## Gate table', '', '| Gate | Status | Evidence |', '|---|---|---|', *rows, '',
        '"Evidence produced" means the automated checks in this packet came out as stated on synthetic fixtures. It does not mean practitioner-approved.', '',
        '## Implemented, tested, practitioner-reviewed', '',
        '- Implemented: deterministic S01 world (#22), three scripted baselines (#23), tool/runner layer with replayable transcripts (#24), independent verifier (#25), and this demonstration composer (`src/supplychainworld/dynamic_demo.py`, `scripts/run_dynamic_demo.py`) for a 5-day and a 15-day fixture.',
        '- Tested: unit tests for each component plus `tests/test_dynamic_demo.py` (packet gates, replay, no-leak scan, determinism). Raw output in `evidence/issue-26/tests.log`.',
        '- Practitioner-reviewed: nothing. Zero assumptions have been reviewed.', '',
        '## Unresolved / needs practitioner review', '', *[f'- {u}' for u in UNRESOLVED], '',
        '## Not claimed', '',
        '- No model ability, generalization or training improvement. One synthetic scenario family with scripted policies.',
        '- No paid model call, bulk teacher data, fine-tuning or live ERP write.',
        '- Expedite being cheapest here is a property of this fixture, not an optimal-policy claim; the alternate policy is valid but costlier.', '',
        shot, '', '## Files', '',
        '- `timeline.txt`, `timeline.html`: chronological agent actions and world events per episode.',
        '- `state-ledger.csv`, `state-ledger.json`: before/after state per day per episode.',
        '- `scorecard.json`, `scorecard.md`: three-policy comparison for both horizons.',
        '- `checks.json`: independent verifier results, corruption cases and rejection probes.',
        '- `replay.json`, `replay.log`: replay command and results.',
        '- `experience-record.json`, `experience-record.md`: one observable record (15-day expedite) without private answers.',
        '- `transcripts.json`: full runner transcripts for all six episodes.', ''])


def report_html(packet, gate_md):
    sc = scorecard_rows(packet)
    head = list(sc[0])
    table = '<table><tr>' + ''.join(f'<th>{h}</th>' for h in head) + '</tr>' + ''.join(
        '<tr>' + ''.join(f'<td>{html.escape(str(r[h]))}</td>' for h in head) + '</tr>' for r in sc) + '</table>'
    return ('<!doctype html><html><head><meta charset="utf-8"><title>S01 demo packet</title>'
            '<style>body{font:14px/1.4 sans-serif;margin:24px;max-width:1500px}table{border-collapse:collapse;font-size:12px}'
            'td,th{border:1px solid #888;padding:3px 6px}pre{background:#f4f4f4;padding:10px;white-space:pre-wrap;font-size:12px}</style></head><body>'
            '<h1>S01 supplier-delay demonstration packet</h1><p>Scripted baselines on synthetic fixtures. No LLM, no practitioner review.</p>'
            f'<h2>Scorecard</h2>{table}<h2>Gate report</h2><pre>{html.escape(gate_md)}</pre>'
            f'<h2>Timeline (5-day expedite excerpt)</h2><pre>{html.escape(timeline_for(packet, "s01-five-day", "expedite"))}</pre></body></html>')


def timeline_for(packet, fid, policy):
    full = timeline_text({'episodes': {fid: {policy: packet['episodes'][fid][policy]}}})
    return full


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='evidence/issue-26')
    ap.add_argument('--screenshot', default='', help='path (relative to repo) of a real screenshot to reference')
    args = ap.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    packet = build_packet()
    tl = timeline_text(packet)
    (out / 'timeline.txt').write_text(tl + '\n')
    (out / 'timeline.html').write_text('<!doctype html><meta charset="utf-8"><title>S01 timeline</title><pre style="font:12px monospace">'
                                       + html.escape(tl) + '</pre>\n')
    rows = ledger_rows(packet)
    (out / 'state-ledger.json').write_text(dumps(rows))
    with (out / 'state-ledger.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    sc = scorecard_rows(packet)
    (out / 'scorecard.json').write_text(dumps(sc))
    (out / 'scorecard.md').write_text('# Three-policy scorecard (scripted baselines, synthetic fixtures)\n\n' + md_table(sc) + '\n')
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
    gate_md = gate_report(packet, args.screenshot)
    (out / 'gate-report.md').write_text(gate_md)
    (out / 'report.html').write_text(report_html(packet, gate_md))
    print(f'wrote {out}; experience {EXPERIENCE_FIXTURE}/{EXPERIENCE_POLICY}; leaks={packet["experience_leaks"]}')
    for k, v in packet['gates'].items():
        print(k, v['pass'])


if __name__ == '__main__':
    main()
