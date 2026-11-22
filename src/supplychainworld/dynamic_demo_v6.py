"""End-to-end demonstration packet for the S01 v0.6 family (issue #19, audit follow-up).

Runs the five declared scripted policies on each of the five scenarios (25 episodes) through the observable tool
runner, checks every episode with the independent v0.6 checker and the hand-worked ledgers, replays every transcript
on a fresh world, scans every observation (and the one published experience record) for private answers and outcome
wording, and reports a PER-METRIC comparison. The comparison never names an overall best policy: cost, service, tier
impact, downstream impact and supply risk are reported separately.

New in v0.6 and shown here: the conventions block is part of what the agent saw (initial observation of the experience
record); the checker's corruption cases include the audit's defects D2 to D6 and a repeated id-less purchase; the
experience record has a plain-language rendering and a STRUCTURAL readability check (sections present, a plain line for
every action, no raw internal ids or private fields). That check does NOT show that a person finds the record readable.

Scripted policies are not LLMs, nothing here measures model ability, and every number is PROVISIONAL, needs
practitioner value. Practitioner review: none (owner review only, not independent).
"""
import json
import re
from copy import deepcopy
from pathlib import Path

from .agent_runner_v6 import POLICIES_V6, ObservableRunnerV6, replay_v6, scripted_policy_v6
from .dynamic_demo_v4 import (FORBIDDEN_KEYS, HAND_METRIC_PATHS, LEDGER_KEYS, METRICS, _get,  # noqa: F401
                              compare_policies, cost_findings, hand_matches)
from .dynamic_v6 import OperationalWorldV6, ScenarioV6
from .dynamic_verifier_v6 import check_observations_for_leaks, verify_episode

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PATH = 'fixtures/dynamic/v0.6/scenarios.json'
HAND_PATH = 'fixtures/dynamic/v0.6/hand-ledgers.json'
PAIR = ('s06-warned-delayed-10d', 's06-warned-no-delay-10d')
EXPERIENCE_FIXTURE, EXPERIENCE_POLICY = 's06-warned-delayed-10d', 'staged_revisit'
EXPERIENCE_SCHEMA = 'dyn19-experience-6'
BANNER = ('ALL NUMBERS PROVISIONAL, needs practitioner value. Scripted policies, synthetic scenarios, no LLM, '
          'practitioner review: none (owner review only, not independent).')


def load_fixtures(root=ROOT):
    return json.loads((Path(root) / FIXTURES_PATH).read_text())['fixtures']


def load_hand(root=ROOT):
    return json.loads((Path(root) / HAND_PATH).read_text())['fixtures']


def factory(fixture, sink=None):
    def make():
        w = OperationalWorldV6(fixture['horizon_days'], scenario=ScenarioV6(**fixture['scenario']))
        if sink is not None:
            sink.append(w)
        return w
    return make


def actions_of(transcript):
    return [{'day': a['day'], 'kind': {'commit_recovery': 'recovery', 'release_production': 'release'}[a['tool']],
             'arguments': a['arguments'], 'result': a['result']}
            for a in transcript['attempts'] if a['tool'] in ('commit_recovery', 'release_production')]


def observations_of(transcript):
    return [{'state': a['view_before']['state'], 'rules': a['view_before']['rules'],
             'last_outcome': a['view_before']['last_outcome']} for a in transcript['attempts']]


def prefix_before_firm_notice(transcript):
    """Everything the agent saw and did before any firm notice was visible (the opaque label and the conventions
    block are part of it, so they must themselves be identical for the paired scenarios)."""
    return [{'view': {k: a['view_before'][k] for k in ('state', 'rules', 'clock', 'last_outcome')},
             'call': {'tool': a['tool'], 'arguments': a['arguments']}, 'result': a['result']}
            for a in transcript['attempts'] if not a['view_before']['state']['notices']]


# ------------------------------------------------------------------ corruption checks

def _alert_index(history):
    return next(i for i, e in enumerate(history)
                if e['kind'] == 'day_open' and (e['state']['signals'] or e['state']['notices']))


def _tamper_checks(fixture, history, scorecard):
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    out = []

    def case(name, hist, card, expect_any, scenario_arg=None):
        r = verify_episode(scenario_arg or scenario, hist, horizon_days=horizon, scorecard=card)
        out.append({'case': name, 'feasible': r.feasible, 'codes': r.codes(), 'expected_any_of': sorted(expect_any),
                    'rejected_as_expected': (not r.feasible) and bool(set(expect_any) & set(r.codes()))})

    forged = deepcopy(scorecard)
    forged['cost']['net_cost'] += 17
    case('forged scorecard net cost', history, forged, {'scorecard_mismatch'})
    h = deepcopy(history)
    next(e for e in h if e['kind'] == 'receipt')['day'] -= 1
    case('premature receipt', h, scorecard, {'receipt_timing_or_quantity'})
    h = deepcopy(history)
    next(e for e in h if e['kind'] == 'day_close')['state']['penalties'] += 7
    case('wrong penalty claimed', h, scorecard, {'penalty_mismatch'})
    h = [e for e in deepcopy(history) if not (e['kind'] == 'day_close' and e['day'] == 2)]
    case('deleted day close', h, scorecard, {'event_day_mismatch', 'missing_event', 'ledger_mismatch'})
    for name, calls, code in (
            ('duplicate commitment (same commit_id executed twice)',
             [{'choice': 'alternate', 'quantity': 1, 'commit_id': 'dup1'}] * 2, 'duplicate_commitment'),
            ('repeated id-less purchase executed twice (same key)',
             [{'choice': 'alternate', 'quantity': 1, 'commit_id': None}] * 2, 'duplicate_commitment'),
            ('over-budget combined recovery',
             [{'choice': 'expedite', 'quantity': 8, 'commit_id': 'big1'},
              {'choice': 'alternate', 'quantity': 8, 'commit_id': 'big2'}], 'budget_exceeded')):
        h = deepcopy(history)
        i = _alert_index(h)
        for k, d in enumerate(calls):
            h.insert(i + 1 + k, {'day': h[i]['day'], 'kind': 'recovery', 'details': d, 'accepted': True,
                                 'reason': None, 'state': deepcopy(h[i]['state'])})
        case(name, h, scorecard, {code})
    # D2: the opening records
    h = deepcopy(history)
    next(e for e in h if e['kind'] == 'day_open' and e['day'] == 2)['state']['component_on_hand'] += 5
    case('forged opening state (day_open)', h, scorecard, {'ledger_mismatch'})
    h = deepcopy(history)
    i = next(k for k, e in enumerate(h) if e['kind'] == 'opening_before_notice' and e['day'] == 2)
    del h[i]
    case('deleted opening record', h, scorecard, {'missing_event', 'ledger_mismatch', 'unexpected_event'})
    # D3: the full state, including the version fields
    h = deepcopy(history)
    next(e for e in h if e['kind'] == 'day_close' and e['day'] == 2)['state']['horizon_days'] += 1
    case('forged horizon in a recorded state', h, scorecard, {'ledger_mismatch'})
    h = deepcopy(history)
    h[0]['state']['schema_version'] = '5.0'
    case('forged schema version in a recorded state', h, scorecard, {'ledger_mismatch'})
    # D4: records that are not mappings must be rejected cleanly
    h = deepcopy(history)
    next(e for e in h if e['kind'] == 'release')['details'] = [None]
    case('non-mapping record details', h, scorecard, {'malformed_event'})
    # D5: a malformed scenario gives the documented error
    try:
        verify_episode(dict(scenario, orders=[1]), history, horizon_days=horizon)
        scenario_ok, scenario_error = False, 'no error'
    except ValueError as exc:
        scenario_ok, scenario_error = True, type(exc).__name__
    out.append({'case': 'malformed scenario orders', 'feasible': False, 'codes': [scenario_error],
                'expected_any_of': ['ScenarioError'], 'rejected_as_expected': scenario_ok and scenario_error == 'ScenarioError'})
    # D6: a malformed action log is rejected cleanly
    r = verify_episode(scenario, history, horizon_days=horizon, scorecard=scorecard, actions=['x', 5])
    out.append({'case': 'malformed action log', 'feasible': r.feasible, 'codes': r.codes(), 'expected_any_of': ['malformed_event'],
                'rejected_as_expected': (not r.feasible) and 'malformed_event' in r.codes()})
    if fixture['scenario']['signal_day'] is not None:
        h = deepcopy(history)
        next(e for e in h if e['kind'] == 'signal')['details']['delayed_arrival_day'] = fixture['scenario']['delayed_arrival_day']
        case('early signal leaks the outcome (event details)', h, scorecard, {'signal_leak'})
        h = deepcopy(history)
        for e in h:
            if e['state']['signals'] and not e['state']['notices']:
                e['state']['signals'][0]['text'] = 'Primary PO will be delayed; firm notice follows'
        case('early signal leaks the outcome (state text)', h, scorecard, {'signal_leak'})
    h = deepcopy(history)
    for e in h:
        e['passed'] = True
    r = verify_episode(scenario, h, horizon_days=horizon, scorecard={**scorecard, 'verified': True})
    out.append({'case': 'forged passed/verified flags', 'feasible': r.feasible, 'codes': r.codes(),
                'ignored_self_reports': r.ignored_self_reports,
                'rejected_as_expected': r.feasible and bool(r.ignored_self_reports)})
    return out


# ------------------------------------------------------------------ one episode

def run_episode(fixture, policy, hand=None):
    world = factory(fixture)()
    transcript = ObservableRunnerV6(world).run(scripted_policy_v6(policy))
    history, card = world.history(), world.scorecard()
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    report = verify_episode(scenario, history, horizon_days=horizon, scorecard=card, actions=actions_of(transcript))
    sink = []
    ok, diffs = replay_v6(transcript, factory(fixture, sink))
    again = sink[-1]
    rep2 = verify_episode(scenario, again.history(), horizon_days=horizon, scorecard=again.scorecard())
    return {'fixture_id': fixture['fixture_id'], 'policy': policy, 'transcript': transcript, 'history': history,
            'scorecard': card, 'report': report,
            'hand': hand_matches(fixture['fixture_id'], policy, report, card, hand or load_hand()),
            'tamper': _tamper_checks(fixture, history, card),
            'leaks': check_observations_for_leaks(scenario, observations_of(transcript)),
            'replay': {'transcript_reproduced': ok, 'differences': diffs,
                       'state_sequence_identical': again.history() == history,
                       'replayed_scorecard_identical': again.scorecard() == card,
                       'replayed_history_feasible': rep2.feasible}}


def paired_identical(episodes):
    """Warned-and-delayed and warned-and-no-delay look identical to the agent until the firm notice."""
    out = {}
    for p in POLICIES_V6:
        a = prefix_before_firm_notice(episodes[PAIR[0]][p]['transcript'])
        b = prefix_before_firm_notice(episodes[PAIR[1]][p]['transcript'])
        out[p] = bool(a) and a == b
    return out


# ------------------------------------------------------------------ the experience record

def experience_record(episode):
    """The structured record of one episode: what the agent saw (including the conventions block), what it did and
    what happened. No answer key, other policy or checker output."""
    t = episode['transcript']
    first = t['initial']['view']
    rec = {'schema': EXPERIENCE_SCHEMA, 'scenario_id': t['scenario_id'], 'horizon_days': t['horizon_days'],
           'agent': 'scripted baseline policy (not an LLM; carries no model-ability claim)',
           'values_status': 'PROVISIONAL, needs practitioner value; practitioner review: none',
           'tool_definitions': first['tools'],
           'initial_observation': {'clock': first['clock'], 'state': first['state'], 'rules': first['rules']},
           'steps': []}
    for a in t['attempts']:
        v = a['view_before']
        rec['steps'].append({
            'seq': a['seq'], 'day': a['day'],
            'observation': {'clock': v['clock'], 'state': v['state'], 'rules': v['rules'], 'last_outcome': v['last_outcome']},
            'action': {'tool': a['tool'], 'arguments': a['arguments']},
            'outcome': {'accepted': a['accepted'], 'category': a['category'], 'reason': a['reason']},
            'state_changes': a['state_changes'], 'events': a['events']})
    rec['final_state'] = t['final_state']
    rec['final_scorecard'] = t['scorecard']
    return rec


def find_private_leaks(record, scenario):
    leaks = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if any(f in str(k).lower() for f in FORBIDDEN_KEYS):
                    leaks.append(f'forbidden key {k!r} at {path}')
                walk(v, f'{path}.{k}')
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f'{path}[{i}]')

    walk(record, '$')
    obs = [record['initial_observation']] + [s['observation'] for s in record['steps']]
    leaks += check_observations_for_leaks(scenario, obs)
    return leaks


_TOOL_WORDS = {'read_state': 'Looked at the plant state.', 'read_recovery_offers': 'Looked at the recovery offers.',
               'read_scorecard': 'Read the final scorecard.'}


def plain_action(step):
    """One plain-language sentence for the action of a step (no ids, no raw argument dicts)."""
    tool, args, out = step['action']['tool'], step['action']['arguments'], step['outcome']
    if tool == 'commit_recovery':
        what = f"buy {args.get('quantity')} units by {args.get('choice')}"
    elif tool == 'release_production':
        what = f"release {args.get('quantity')} units into production"
    elif tool == 'advance_day':
        what = f"close day {step['day']} and move on"
    else:
        return _TOOL_WORDS.get(tool, 'Used a read tool.')
    if out['accepted']:
        return f'Chose to {what}. Done.'
    return f"Tried to {what}. Refused: {out['reason']}."


def _day_facts(step):
    st = step['observation']['state']
    facts = [f"day {st['day']} of {step['observation']['clock']['horizon_days']}",
             f"{st['component_on_hand']} components and {st['finished_on_hand']} finished goods on hand",
             f"{st['delivered_total']} units delivered so far"]
    if st['signals'] and not st['notices']:
        facts.append(f"a possible-delay signal at level {st['signals'][-1]['level']}")
    for n in st['notices']:
        facts.append(n['text'])
    return '; '.join(facts)


def experience_plain(rec):
    """Markdown for a person: sections for the situation, what the agent was told, day by day, and the result."""
    rules = rec['initial_observation']['rules']
    block = rules['conventions']['statements']
    card = rec['final_scorecard']
    lines = ['# What the agent saw and did', '',
             f"Agent: {rec['agent']}. Values: {rec['values_status']}.", '',
             'This page shows only what the agent could see, the call it made and the outcome. Nothing from the checker, '
             'from other policies or from the scenario\'s future is included.', '',
             '## The situation', '',
             f"A small plant runs for {rec['horizon_days']} simulated days. It has a daily production capacity of "
             f"{rules['capacity']} units and a recovery budget of USD {rules['recovery_budget']}. "
             f"Customer orders: " + '; '.join(
                 f"{o['order_id']} is {o['quantity']} units due on day {o['due_day']} in the {o['tier']} tier"
                 for o in rules['orders']) + '.', '',
             '## The rules the agent was told', '']
    lines += [f'- {s}' for s in block.values()]
    lines += ['', '## Day by day', '']
    for s in rec['steps']:
        lines.append(f"- Step {s['seq']}. Situation: {_day_facts(s)}. {plain_action(s)}")
    srv, cost = card['service'], card['cost']
    lines += ['', '## The result', '',
              f"{srv['otif_orders_met']} of {srv['orders_total']} orders were delivered in full on time. "
              f"{srv['delivered_total']} units were delivered, {srv['cancelled_units']} were cancelled, and "
              f"{srv['unit_days_late']} unit-days were late. Recovery spend was USD {cost['recovery_spend']}, late "
              f"penalties USD {cost['service_penalties']}, salvage credit USD {cost['salvage_credit']}, so the net cost "
              f"was USD {cost['net_cost']}. All numbers are PROVISIONAL, needs practitioner value.", '']
    return '\n'.join(lines) + '\n'


READABILITY_SECTIONS = ('# What the agent saw and did', '## The situation', '## The rules the agent was told',
                        '## Day by day', '## The result')
_RAW_PATTERNS = (r'auto-[0-9a-f]{8}', r'scn-[0-9a-f]{8}', r's0\d-\w+-\d+d', r'\bcommit_id\b', r'\blot_id\b',
                 r'\bscenario_id\b', r"\{'", r'\[\{', r'\bNone\b', r'\bTrue\b', r'\bFalse\b')


def readability_check(rec, text):
    """STRUCTURAL check of the plain-language rendering. Returns a list of problems (empty: structure is fine).

    It checks that every section is present, that every action of the record has a plain line, that no raw internal id,
    Python object text or private field name appears, and that the lines are not unreasonably long. It does NOT show
    that a person finds the record readable or useful; only a person can judge that."""
    problems = [f'missing section {s!r}' for s in READABILITY_SECTIONS if s not in text]
    step_lines = [ln for ln in text.splitlines() if ln.startswith('- Step ')]
    if len(step_lines) != len(rec['steps']):
        problems.append(f"{len(step_lines)} step lines for {len(rec['steps'])} actions")
    for s, ln in zip(rec['steps'], step_lines):
        if plain_action(s) not in ln:
            problems.append(f"step {s['seq']} has no plain line for its action")
    for pat in _RAW_PATTERNS:
        m = re.search(pat, text)
        if m:
            problems.append(f'raw internal text {m.group(0)!r} in the record')
    low = text.lower()
    problems += [f'private field name {k!r} in the record' for k in FORBIDDEN_KEYS if k in low]
    problems += [f'line over 700 characters: {ln[:40]!r}' for ln in text.splitlines() if len(ln) > 700]
    return problems


# ------------------------------------------------------------------ failure behaviour through the tools

def rejection_probes():
    fixture = next(f for f in load_fixtures() if f['fixture_id'] == 's06-sudden-5d')
    runs = {
        'sudden 5d: hidden probe, duplicate action id, repeat without an id, reserved id, over-budget combination, exhausted offers, overcapacity, duplicate release': [
            {'tool': 'read_scenario'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 4}, 'action_id': 'a1'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 4}, 'action_id': 'a1'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 2}},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 2}},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 1}, 'action_id': 'auto-12345678'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 8}, 'action_id': 'a2'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 8}, 'action_id': 'a3'},
            {'tool': 'release_production', 'arguments': {'quantity': 9}},
            {'tool': 'release_production', 'arguments': {'quantity': 4}},
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'}],
        'sudden 5d: window closed on day 3, production without material': [
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'},
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 2}},
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'}],
    }
    out = []
    for name, calls in runs.items():
        world = factory(fixture)()
        it = iter(calls)
        t = ObservableRunnerV6(world).run(lambda v: next(it, None))
        rep = verify_episode(fixture['scenario'], world.history(), horizon_days=fixture['horizon_days'])
        rejected = [a for a in t['attempts'] if not a['accepted']]
        out.append({'run': name,
                    'attempts': [{'seq': a['seq'], 'day': a['day'], 'tool': a['tool'], 'arguments': a['arguments'],
                                  'accepted': a['accepted'], 'category': a['category'], 'reason': a['reason'],
                                  'state_changes': a['state_changes']} for a in t['attempts']],
                    'rejected_count': len(rejected),
                    'rejections_left_state_unchanged': all(not a['state_changes'] for a in rejected),
                    'rejections_audited': all(a['result'] == {'accepted': False, 'reason': a['reason']} for a in rejected),
                    'verifier_feasible': rep.feasible, 'verifier_codes': rep.codes()})
    return out


# ------------------------------------------------------------------ packet and gates

def build_packet():
    fixtures, hand = load_fixtures(), load_hand()
    episodes = {f['fixture_id']: {p: run_episode(f, p, hand) for p in POLICIES_V6} for f in fixtures}
    probes = rejection_probes()
    exp_fix = next(f for f in fixtures if f['fixture_id'] == EXPERIENCE_FIXTURE)
    record = experience_record(episodes[EXPERIENCE_FIXTURE][EXPERIENCE_POLICY])
    plain = experience_plain(record)
    packet = {'fixtures': fixtures, 'episodes': episodes, 'probes': probes, 'experience': record,
              'experience_plain': plain, 'experience_leaks': find_private_leaks(record, exp_fix['scenario']),
              'readability_problems': readability_check(record, plain),
              'all_episode_leaks': {f'{fid}/{p}': ep['leaks'] for fid, ps in episodes.items() for p, ep in ps.items() if ep['leaks']},
              'comparison': {fid: compare_policies(eps) for fid, eps in episodes.items()},
              'paired_signal_identical': paired_identical(episodes), 'cost_findings': cost_findings(episodes)}
    packet['gates'] = evaluate_gates(packet)
    return packet


def evaluate_gates(packet):
    fixtures, episodes = packet['fixtures'], packet['episodes']
    every = [(fid, p, ep) for fid, ps in episodes.items() for p, ep in ps.items()]
    g = {}
    g['G1'] = {'pass': all(ep['transcript']['initial']['view']['state']['day'] == 1
                           and ep['transcript']['initial']['view']['rules']['orders']
                           and ep['transcript']['initial']['view']['rules']['conventions']['statements'] for _, _, ep in every),
               'evidence': 'Initial observation (state, contract terms by order, tier rules, salvage rate, budget, the conventions block, tool definitions, schema and runtime version) recorded per episode in transcripts.json.'}
    clock = True
    for fid, p, ep in every:
        h = ep['history']
        n = next(f['horizon_days'] for f in fixtures if f['fixture_id'] == fid)
        clock &= [e['day'] for e in h if e['kind'] == 'day_open'] == list(range(1, n + 1)) \
            == [e['day'] for e in h if e['kind'] == 'day_close'] and h[-1]['kind'] == 'episode_complete'
    g['G2'] = {'pass': clock, 'evidence': 'Every episode logs day_open then day_close for each day 1..horizon (5 and 10) and ends with episode_complete.'}
    g3 = True
    for fid, ps in episodes.items():
        sc = next(f for f in fixtures if f['fixture_id'] == fid)['scenario']
        for p, ep in ps.items():
            sig = [e for e in ep['history'] if e['kind'] == 'signal']
            notice = [e for e in ep['history'] if e['kind'] == 'notice']
            g3 &= len(notice) == 1 and notice[0]['day'] == sc['notice_day']
            g3 &= len(sig) == (1 if sc['signal_day'] else 0) and all(s['day'] == sc['signal_day'] for s in sig)
            g3 &= notice[0]['details']['kind'] == ('delay_confirmed' if sc['delay_outcome'] == 'delay' else 'on_time_confirmed')
    g['G3'] = {'pass': g3, 'evidence': 'Sudden scenarios show only a firm notice; warned scenarios show a possible-delay signal first and a firm notice later that either confirms a delay or confirms on-time arrival. Commitments change lot timing and create distinct lots (see timeline.txt).'}
    g['G4'] = {'pass': all(ep['report'].feasible and ep['hand']['ledger'] for _, _, ep in every),
               'evidence': 'The independent v0.6 per-day ledger equals the hand-worked ledgers for all 25 episodes (received, produced, shipped, stock, delivered, penalties, spend, cancellations) and passes conservation checks. The hand ledgers come from scripts/generate_hand_ledgers_v06.py, which imports no project code.'}
    g['G5'] = {'pass': all(ep['hand']['metrics'] and ep['hand']['tiers'] for _, _, ep in every),
               'evidence': 'Per-metric scorecards (cost, service, tier impact, downstream, supply risk) equal the hand-worked per-episode metrics. Same initial world and disruption per scenario across the five declared policies.'}
    tamper_ok = all(t['rejected_as_expected'] for _, _, ep in every for t in ep['tamper'])
    g['G6'] = {'pass': tamper_ok,
               'evidence': 'dynamic_verifier_v6 re-derives each episode from commands and imports no simulator code (AST test). Corruption cases per episode: forged scorecard, premature receipt, wrong penalty, deleted close, duplicate commitment, repeated id-less purchase, over-budget combination, forged opening state, deleted opening record, forged horizon and version fields, non-mapping details, malformed scenario, malformed action log, leaked signal (warned scenarios), forged pass flags.'}
    probes_ok = all(p['rejected_count'] >= 3 and p['rejections_left_state_unchanged'] and p['rejections_audited']
                    and p['verifier_feasible'] for p in packet['probes'])
    g['G7'] = {'pass': probes_ok, 'partial': True,
               'evidence': 'Through the tool interface: hidden-state probe, duplicate action id, the same purchase repeated without an id, a reserved id, over-budget combination, overcapacity, duplicate release, closed offer window, production without material. Each rejection leaves state unchanged and stays auditable. Premature receipt, wrong penalty and leaked signals are proven at checker level.'}
    replay_ok = all(ep['replay']['transcript_reproduced'] and ep['replay']['state_sequence_identical']
                    and ep['replay']['replayed_scorecard_identical'] and ep['replay']['replayed_history_feasible']
                    for _, _, ep in every)
    g['G8'] = {'pass': replay_ok and not packet['experience_leaks'] and not packet['all_episode_leaks']
               and all(packet['paired_signal_identical'].values()),
               'evidence': 'Each transcript replays from recorded calls with identical state sequence and scorecard. All observations in all 25 episodes (conventions block included) pass the private-answer and outcome-leak scan; warned-and-delayed and warned-and-no-delay episodes are observation-identical until the firm notice.'}
    g['G9'] = {'pass': None, 'evidence': 'Labels and limitations published. No practitioner review has occurred (owner review only, not independent); the gate cannot be called passed.'}
    return g
