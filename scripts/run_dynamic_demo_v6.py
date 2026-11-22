#!/usr/bin/env python3
"""Run the S01 v0.6 family demonstration (issue #19, audit follow-up) and write the evidence packet.

Usage: PYTHONPATH=src python scripts/run_dynamic_demo_v6.py [--out evidence/s01-v06]
Deterministic: no clock, randomness, network or model calls enter the packet. Writes timeline, per-day ledgers,
scorecards, per-metric comparison, checker results, replay results, one experience record (structured and in plain
language, with its structural readability check), the gate report and `report.html` (a self-contained page with no
script and no outside resource).
"""
import argparse
import csv
import html
import json
from pathlib import Path

from supplychainworld.agent_runner_v6 import POLICIES_V6
from supplychainworld.dynamic_demo_v6 import (BANNER, EXPERIENCE_FIXTURE, EXPERIENCE_POLICY, METRICS, READABILITY_SECTIONS,
                                              build_packet)

ROOT = Path(__file__).resolve().parents[1]
REPLAY_CMD = 'PYTHONPATH=src python scripts/run_dynamic_demo_v6.py --out evidence/s01-v06'
TITLE = 'S01 v0.6 packet'
H1 = 'S01 v0.6 family demonstration packet'
GATE_TITLES = {'G1': 'Coherent initial world', 'G2': 'Actual time progression', 'G3': 'Executed disruption, signal and recovery',
               'G4': 'Consequential state changes (hand ledgers)', 'G5': 'Per-metric scorecards (hand metrics)',
               'G6': 'Independent checking', 'G7': 'Failure behavior', 'G8': 'Replay and no-leak', 'G9': 'Honest demonstration'}


def dumps(obj):
    return json.dumps(obj, indent=1) + '\n'


def fmt_event(e):
    d = ', '.join(f'{k}={v}' for k, v in e['details'].items())
    flag = '' if e['accepted'] else f" REJECTED ({e['reason']})"
    return f"day {e['day']} {e['kind']}{(' ' + d) if d else ''}{flag}"


def attempt_line(a):
    args = ','.join(f'{k}={v}' for k, v in a['arguments'].items())
    verdict = 'accepted' if a['accepted'] else f"REJECTED ({a['reason']})"
    return f"#{a['seq']:02d} day {a['day']} agent calls {a['tool']}({args}) -> {verdict}"


def episode_header(fid, policy, t):
    return f"=== {fid} / {policy} (horizon {t['horizon_days']} days, status {t['status']}) ==="


def timeline_text(packet):
    lines = ['S01 v0.6 timeline. ' + BANNER, '']
    for fid, runs in packet['episodes'].items():
        for policy, ep in runs.items():
            t = ep['transcript']
            lines += [episode_header(fid, policy, t), 'initial events:']
            lines += ['  ' + fmt_event(e) for e in t['initial']['events']]
            for a in t['attempts']:
                lines.append(attempt_line(a))
                lines += ['      ' + fmt_event(e) for e in a['events']]
            lines += [f"final scorecard: {json.dumps(t['scorecard'])}", '']
    return '\n'.join(lines)


def ledger_rows(packet):
    return [{'fixture': fid, 'policy': policy, **r} for fid, runs in packet['episodes'].items()
            for policy, ep in runs.items() for r in ep['report'].ledger]


def flat_scorecard_rows(packet):
    rows = []
    for fid, runs in packet['episodes'].items():
        for p in POLICIES_V6:
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


def findings_md(packet):
    f = packet['cost_findings']
    pols = list(POLICIES_V6)
    out = ['## Net cost by scenario and policy (USD, lower is better)', '',
           'Net cost = expedite spend + alternate spend + penalties - salvage. It is one metric beside the others, not a ranking.', '',
           '| scenario | ' + ' | '.join(pols) + ' | cheapest on net cost |', '|' + '---|' * (2 + len(pols))]
    for fid, row in f.items():
        out.append(f'| {fid} | ' + ' | '.join(str(row['net_cost'][p]) for p in pols) + ' | '
                   + ', '.join(row['cheapest_policy_on_net_cost']) + ' |')
    wins = sum(1 for r in f.values() if r['maintain_wins_net_cost'])
    out += ['', f'Maintain has the lowest net cost in {wins} of {len(f)} scenarios. This is a finding of the provisional numbers, '
            'not a recommendation; service, tier, downstream and supply-risk metrics are reported separately below. '
            'No overall winner is declared.', '']
    return out


def comparison_md(packet):
    out = ['# Per-metric comparison (no overall winner is declared)', '', BANNER, '', *findings_md(packet),
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
    out = {'note': 'Checker results re-derived from recorded commands; self-reported pass flags are ignored. ' + BANNER,
           'episodes': {}}
    for fid, runs in packet['episodes'].items():
        out['episodes'][fid] = {}
        for p, ep in runs.items():
            r = ep['report']
            out['episodes'][fid][p] = {'feasible': r.feasible, 'complete': r.complete, 'violations': r.violations,
                                       'matches_hand_worked': ep['hand'], 'derived_scorecard': r.scorecard,
                                       'ignored_self_reports': r.ignored_self_reports, 'corruption_cases': ep['tamper'],
                                       'observation_leaks': ep['leaks']}
    out['rejection_probes'] = packet['probes']
    out['paired_signal_identical_until_firm_notice'] = packet['paired_signal_identical']
    out['leak_scan'] = {'experience_record': packet['experience_leaks'], 'all_episodes': packet['all_episode_leaks']}
    return out


def replay_json(packet):
    return {'command': REPLAY_CMD,
            'method': 'Recorded tool calls re-driven through a fresh ObservableRunnerV6 and world; views, outcomes, state changes, final state and scorecard must match exactly. The replayed history is also compared and re-verified.',
            'episodes': {fid: {p: {**ep['replay'], 'attempts': len(ep['transcript']['attempts'])} for p, ep in runs.items()}
                         for fid, runs in packet['episodes'].items()}}


def readability_json(packet):
    return {'experience': f'{EXPERIENCE_FIXTURE} / {EXPERIENCE_POLICY}', 'sections_required': list(READABILITY_SECTIONS),
            'actions_in_record': len(packet['experience']['steps']), 'problems': packet['readability_problems'],
            'what_this_shows': 'A STRUCTURAL check of experience-record.md: every section is present, every action has a plain-language line, no raw internal ids, Python object text or private field names appear.',
            'what_this_does_not_show': 'It does not show that a person finds the record readable, clear or useful. No person has been asked.'}


def gate_report(packet):
    rows = []
    for k, title in GATE_TITLES.items():
        v = packet['gates'][k]
        status = 'Evidence produced, unreviewed' if v['pass'] else ('Partial: labels stated; practitioner review none' if v['pass'] is None else 'FAILED')
        rows.append(f"| {k} {title} | {status} | {v['evidence']} |")
    return '\n'.join([
        '# S01 v0.6 gate report', '', BANNER, '',
        'Regenerate: `' + REPLAY_CMD + '`. Output is deterministic.', '',
        '| Gate | Status | Evidence |', '|---|---|---|', *rows, '',
        'Implemented: yes. Tested: yes (automated, synthetic fixtures). Practitioner-reviewed: no.', '',
        'No model-ability claim. No overall best policy is declared. The warned scenarios use an authored hint value that is not calibrated.', ''])


# ------------------------------------------------------------------ the page

CSS = """
:root{--bg:#fbfaf8;--fg:#1d1d1b;--muted:#5d5b55;--card:#fff;--line:#dedad2;--accent:#1f5f8b;--warn:#8a4b00;--warnbg:#fff4e0}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#16171a;--fg:#ececea;--muted:#a3a29c;--card:#1f2024;--line:#35363b;--accent:#6fb1e0;--warn:#f0b35c;--warnbg:#33290f}}
:root[data-theme="dark"]{--bg:#16171a;--fg:#ececea;--muted:#a3a29c;--card:#1f2024;--line:#35363b;--accent:#6fb1e0;--warn:#f0b35c;--warnbg:#33290f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 8px}h2{font-size:20px;margin:36px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}h3{font-size:16px;margin:22px 0 6px}
.banner{background:var(--warnbg);color:var(--warn);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
nav a{color:var(--accent);margin-right:14px;text-decoration:none}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:5px 9px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{background:color-mix(in srgb,var(--card) 88%,var(--fg) 12%)}td.num{text-align:right;font-variant-numeric:tabular-nums}
.metric-block{margin:0 0 16px}details{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:8px 0;padding:6px 12px}
summary{cursor:pointer;font-weight:600}ol.timeline{margin:8px 0;padding-left:34px;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
ol.timeline li{overflow-wrap:anywhere}.muted{color:var(--muted)}pre.plain{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
ul.conv li{margin:4px 0}.ok{color:#1b7a3a}.bad{color:#b3261e;font-weight:700}
"""


def _table(headers, rows, attrs=''):
    head = ''.join(f'<th>{html.escape(str(h))}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(
        f'<td class="{"num" if isinstance(c, (int, float)) and not isinstance(c, bool) else ""}">{html.escape(str(c))}</td>' for c in r)
        + '</tr>' for r in rows)
    return f'<div class="scroll"><table {attrs}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def report_html(packet, text):
    sc = flat_scorecard_rows(packet)
    cols = list(sc[0])
    parts = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>{TITLE}</title><style>{CSS}</style></head><body><main>',
             f'<h1>{H1}</h1><p class="banner" id="banner">{html.escape(BANNER)}</p>',
             '<nav><a href="#scorecard">Scorecards</a><a href="#comparison">Per-metric comparison</a><a href="#conventions">Conventions the agent sees</a>'
             '<a href="#experience">Experience record</a><a href="#checks">Checks</a><a href="#gates">Gates</a><a href="#timeline">Timeline</a></nav>']
    parts.append('<h2 id="scorecard">Scorecards</h2><p class="muted">One row per scenario and policy. Cost, service, tier, downstream and supply-risk metrics are separate columns, never merged.</p>')
    parts.append(_table(cols, [[r[c] for c in cols] for r in sc], 'id="scorecard-table"'))
    parts.append('<h2 id="comparison">Per-metric comparison</h2><p class="muted" id="no-winner">No overall winner is declared. Each block lists the policy that is best on that metric alone.</p>')
    for fid, c in packet['comparison'].items():
        pols = list(next(iter(c['metrics'].values()))['values'])
        rows = [[m, row['dimension'], row['better'], *[row['values'][p] for p in pols], ', '.join(row['best_on_this_metric_alone'])]
                for m, row in c['metrics'].items()]
        parts.append(f'<div class="metric-block" data-fixture="{html.escape(fid)}"><h3>{html.escape(fid)}</h3>'
                     + _table(['metric', 'dimension', 'better', *pols, 'best here'], rows)
                     + f"<p class=\"muted\">Best on every metric: {html.escape(str(c['best_on_every_metric'] or 'none'))}. {html.escape(c['trade_offs'] or '')}</p></div>")
    first = next(iter(packet['episodes'].values()))[POLICIES_V6[0]]['transcript']['initial']['view']['rules']['conventions']
    parts.append('<h2 id="conventions">Conventions the agent is told</h2><p class="muted">Shown to the agent in every observation under rules.conventions, built from the world itself.</p><ul class="conv">'
                 + ''.join(f'<li><b>{html.escape(k)}</b>: {html.escape(v)}</li>' for k, v in first['statements'].items()) + '</ul>')
    parts.append(f'<h2 id="experience">Experience record ({html.escape(EXPERIENCE_FIXTURE)} / {html.escape(EXPERIENCE_POLICY)})</h2>'
                 '<p class="muted">Plain-language rendering of what the agent saw and did. The readability check below it is structural only.</p>'
                 f'<pre class="plain" id="experience-plain">{html.escape(packet["experience_plain"])}</pre>'
                 f'<p id="readability">Structural readability check: {"no problems found" if not packet["readability_problems"] else html.escape("; ".join(packet["readability_problems"]))}. '
                 'This does not show that a person finds the record readable.</p>')
    rows = [[fid, p, ep['report'].feasible, all(ep['hand'].values()), ep['replay']['transcript_reproduced'], not ep['leaks'],
             sum(1 for t in ep['tamper'] if t['rejected_as_expected']) == len(ep['tamper'])]
            for fid, runs in packet['episodes'].items() for p, ep in runs.items()]
    parts.append('<h2 id="checks">Checks per episode</h2>' + _table(
        ['scenario', 'policy', 'checker feasible', 'matches hand ledger', 'replay reproduced', 'leak scan clean', 'corruption cases rejected'], rows,
        'id="checks-table"'))
    parts.append('<h2 id="gates">Gates</h2>' + _table(['gate', 'status', 'evidence'], [
        [f'{k} {t}', 'Evidence produced, unreviewed' if packet['gates'][k]['pass'] else ('Partial: labels stated; practitioner review none' if packet['gates'][k]['pass'] is None else 'FAILED'),
         packet['gates'][k]['evidence']] for k, t in GATE_TITLES.items()], 'id="gates-table"'))
    parts.append('<h2 id="timeline">Timeline</h2><p class="muted">Every call of every episode, in order.</p>')
    for fid, runs in packet['episodes'].items():
        for policy, ep in runs.items():
            t = ep['transcript']
            items = ''.join(f'<li class="attempt">{html.escape(attempt_line(a))}</li>' for a in t['attempts'])
            parts.append(f'<details data-fixture="{html.escape(fid)}" data-policy="{html.escape(policy)}"><summary>{html.escape(episode_header(fid, policy, t))}</summary>'
                         f'<ol class="timeline">{items}</ol></details>')
    parts.append('</main></body></html>\n')
    return ''.join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='evidence/s01-v06')
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
    (out / 'experience-record.md').write_text(packet['experience_plain'])
    (out / 'readability-check.json').write_text(dumps(readability_json(packet)))
    (out / 'transcripts.json').write_text(dumps({fid: {p: ep['transcript'] for p, ep in runs.items()}
                                                  for fid, runs in packet['episodes'].items()}))
    gate_md = gate_report(packet)
    (out / 'gate-report.md').write_text(gate_md)
    (out / 'report.html').write_text(report_html(packet, tl))
    print(f'wrote {out}; experience {EXPERIENCE_FIXTURE}/{EXPERIENCE_POLICY}; leaks={packet["experience_leaks"]}; '
          f'readability problems={packet["readability_problems"]}')
    for k, v in packet['gates'].items():
        print(k, v['pass'])


if __name__ == '__main__':
    main()
