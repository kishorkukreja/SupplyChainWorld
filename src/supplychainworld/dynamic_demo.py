"""End-to-end S01 demonstration packet (issue #26, DYN05).

Runs the three scripted baseline policies on every dynamic fixture through the
observable tool runner, checks each recorded episode with the independent
verifier, replays each transcript on a fresh world, and assembles the evidence
packet (timeline, ledger, scorecard, checks, replay, one observable experience
record, gate results).

This module only composes existing components. Scripted policies are not LLMs,
nothing here measures model ability, and the fixture assumptions are unreviewed
by practitioners.
"""
import json
from copy import deepcopy
from pathlib import Path

from .agent_runner import ObservableRunner, replay, scripted_policy
from .dynamic import OperationalWorld, SupplierDelayScenario
from .dynamic_verifier import verify_episode

ROOT = Path(__file__).resolve().parents[2]
POLICIES = ('maintain', 'expedite', 'alternate')
SCORE_KEYS = ('delivered_on_time', 'delivered_total', 'ending_components',
              'incremental_spend', 'service_penalties', 'comparison_cost')
LEDGER_KEYS = ('received', 'produced', 'shipped', 'components_close', 'finished_close',
               'delivered_total', 'penalty_total', 'spend_total', 'undelivered_assessed')
EXPERIENCE_FIXTURE, EXPERIENCE_POLICY = 's01-fifteen-day-late-events', 'expedite'
EXPERIENCE_SCHEMA = 'dyn05-experience-1'

# Names that exist only in private answer keys or scenario configuration.
FORBIDDEN_KEYS = ('expected', 'oracle', 'answer', 'hidden', 'private', 'reference', 'event_days',
                  'backlog_on_assessment', 'delay_notice_day', 'delayed_arrival_day',
                  'initially_promised_day', 'recovery_deadline_day', 'disruption_enabled',
                  'opening_components', 'comparison_cost_by_policy', 'verifier', 'hand_ledger')


def load_fixtures(root=ROOT):
    return json.loads((Path(root) / 'fixtures/dynamic/supplier-delay-inputs.json').read_text())['fixtures']


def _factory(fixture, sink=None):
    def make():
        w = OperationalWorld(fixture['horizon_days'], scenario=SupplierDelayScenario(**fixture['scenario']))
        if sink is not None:
            sink.append(w)
        return w
    return make


def _tamper_checks(fixture, world_history, scorecard):
    """Run the verifier on deliberately corrupted copies; each must be rejected."""
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    out = []

    def case(name, history, card, expect_code):
        r = verify_episode(scenario, history, horizon_days=horizon, scorecard=card)
        out.append({'case': name, 'feasible': r.feasible, 'codes': r.codes(), 'expected_code': expect_code,
                    'rejected_as_expected': (not r.feasible) and expect_code in r.codes()})

    case('forged scorecard cost', world_history, {**scorecard, 'comparison_cost': 0}, 'scorecard_mismatch')
    h = deepcopy(world_history)
    first = next(e for e in h if e['kind'] == 'receipt')
    first['day'] -= 1
    case('premature receipt', h, scorecard, 'receipt_timing_or_quantity')
    h = deepcopy(world_history)
    first = next(e for e in h if e['kind'] == 'day_close' and e['details']['produced'] > 0)
    first['details']['produced'] += 1
    first['state']['finished_on_hand'] += 1
    case('overproduction claimed', h, scorecard, 'ledger_mismatch')
    h = deepcopy(world_history)
    h = [e for e in h if not (e['kind'] == 'day_close' and e['day'] == 2)]
    case('deleted day close', h, scorecard, 'ledger_mismatch')
    h = deepcopy(world_history)
    for e in h:
        e['passed'] = True
    r = verify_episode(scenario, h, horizon_days=horizon, scorecard={**scorecard, 'verified': True})
    out.append({'case': 'forged passed/verified flags', 'feasible': r.feasible, 'codes': r.codes(),
                'ignored_self_reports': r.ignored_self_reports,
                'rejected_as_expected': r.feasible and bool(r.ignored_self_reports)})
    return out


def run_episode(fixture, policy):
    """One baseline run through the tool runner, verifier check and independent replay."""
    world = _factory(fixture)()
    runner = ObservableRunner(world)
    transcript = runner.run(scripted_policy(policy))
    history = world.history()
    scorecard = world.scorecard()
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    actions = [{'day': a['day'], 'kind': {'commit_recovery': 'recovery', 'release_production': 'release'}[a['tool']],
                'arguments': a['arguments'], 'result': a['result']}
               for a in transcript['attempts'] if a['tool'] in ('commit_recovery', 'release_production')]
    report = verify_episode(scenario, history, horizon_days=horizon, scorecard=scorecard, actions=actions)
    # Replay from the recorded calls only, on a fresh world, then compare worlds.
    sink = []
    ok, diffs = replay(transcript, _factory(fixture, sink))
    replay_history = sink[-1].history()
    replay_report = verify_episode(scenario, replay_history, horizon_days=horizon, scorecard=sink[-1].scorecard())
    return {'fixture_id': fixture['fixture_id'], 'policy': policy, 'transcript': transcript,
            'history': history, 'scorecard': scorecard, 'report': report, 'tamper': _tamper_checks(fixture, history, scorecard),
            'replay': {'transcript_reproduced': ok, 'differences': diffs,
                       'state_sequence_identical': replay_history == history,
                       'replayed_scorecard_identical': sink[-1].scorecard() == scorecard,
                       'replayed_history_feasible': replay_report.feasible}}


# ---------------------------------------------------------------- failure behavior

def rejection_probes():
    """Illegal tool calls on the 5-day fixture. Each rejection must leave state unchanged."""
    fixture = load_fixtures()[0]
    runs = {
        'expedite path: hidden-state probe, overcapacity, duplicate commitments': [
            {'tool': 'read_scenario'}, {'tool': 'release_production', 'arguments': {'quantity': 9}},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate'}},
            {'tool': 'release_production', 'arguments': {'quantity': 4}},
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'}],
        'maintain path: late recovery and production without material': [
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}},
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'}],
    }
    out = []
    for name, calls in runs.items():
        world = _factory(fixture)()
        it = iter(calls)
        t = ObservableRunner(world).run(lambda v: next(it, None))
        rep = verify_episode(fixture['scenario'], world.history(), horizon_days=fixture['horizon_days'])
        rejected = [a for a in t['attempts'] if not a['accepted']]
        out.append({'run': name, 'attempts': [{'seq': a['seq'], 'day': a['day'], 'tool': a['tool'],
                                               'arguments': a['arguments'], 'accepted': a['accepted'],
                                               'category': a['category'], 'reason': a['reason'],
                                               'state_changes': a['state_changes']} for a in t['attempts']],
                    'rejected_count': len(rejected),
                    'rejections_left_state_unchanged': all(not a['state_changes'] for a in rejected),
                    'rejections_audited': all(a['result'] == {'accepted': False, 'reason': a['reason']} and a['seq'] for a in rejected),
                    'verifier_feasible': rep.feasible, 'verifier_codes': rep.codes()})
    return out


# ---------------------------------------------------------------- experience record

def experience_record(episode):
    """What the agent actually saw and did. No answer keys, no other policies, no verifier output."""
    t = episode['transcript']
    first = t['initial']['view']
    record = {'schema': EXPERIENCE_SCHEMA, 'scenario_id': t['scenario_id'], 'horizon_days': t['horizon_days'],
              'agent': 'scripted baseline policy (not an LLM; carries no model-ability claim)',
              'tool_definitions': first['tools'],
              'initial_observation': {'clock': first['clock'], 'state': first['state'], 'rules': first['rules']},
              'steps': []}
    for a in t['attempts']:
        v = a['view_before']
        record['steps'].append({
            'seq': a['seq'], 'day': a['day'],
            'observation': {'clock': v['clock'], 'state': v['state'], 'rules': v['rules'], 'last_outcome': v['last_outcome']},
            'action': {'tool': a['tool'], 'arguments': a['arguments']},
            'outcome': {'accepted': a['accepted'], 'category': a['category'], 'reason': a['reason']},
            'state_changes': a['state_changes'], 'events': a['events']})
    record['final_state'] = t['final_state']
    record['final_scorecard'] = t['scorecard']
    return record


def find_private_leaks(record, scenario=None):
    """Return a list of leak descriptions (empty means none found)."""
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
    chosen = {s['action']['arguments'].get('choice') for s in record['steps'] if s['action']['tool'] == 'commit_recovery'}
    if len(chosen) > 1:
        leaks.append('more than one policy appears in one record')
    steps = [{'observation': record['initial_observation']}] + record['steps']
    for s in steps:
        obs = s['observation']
        if not obs['state']['notices'] and 'recovery_offers' in obs['rules']:
            leaks.append('recovery offers visible before the delay notice')
        if scenario and not obs['state']['notices'] and obs['state']['recovery'] is None \
                and obs['state']['primary_arrival_day'] != scenario['initially_promised_day']:
            leaks.append('delayed arrival day visible before the notice')
    if scenario and record['steps']:
        pre = [s for s in steps if not s['observation']['state']['notices']]
        text = json.dumps([x['observation'] for x in pre])
        if f"to day {scenario['delayed_arrival_day']}" in text:
            leaks.append('delay text visible before the notice')
    return leaks


# ---------------------------------------------------------------- gates

def _hand():
    return json.loads((ROOT / 'fixtures/dynamic/verifier-hand-ledgers.json').read_text())


def _expected():
    return json.loads((ROOT / 'fixtures/dynamic/supplier-delay-expected.json').read_text())['fixtures']


def ledger_matches_hand(fixture_id, policy, report):
    hand = _hand()[fixture_id][policy]
    return all([r[k] for r in report.ledger] == hand[k] for k in LEDGER_KEYS)


def scorecard_matches_expected(fixture_id, policy, card):
    e = _expected()[fixture_id]['policies'][policy]
    return (card['delivered_on_time'], card['delivered_total'], card['incremental_spend'],
            card['service_penalties'], card['comparison_cost']) == \
           (e['on_time'], e['delivered'], e['spend'], e['penalties'], e['cost'])


DOC_TABLE_5DAY = {'maintain': (120, 4, 0), 'expedite': (24, 12, 0), 'alternate': (40, 12, 8)}  # cost, on time, ending C


def build_packet():
    fixtures = load_fixtures()
    episodes = {f['fixture_id']: {p: run_episode(f, p) for p in POLICIES} for f in fixtures}
    probes = rejection_probes()
    exp_ep = episodes[EXPERIENCE_FIXTURE][EXPERIENCE_POLICY]
    exp_fix = next(f for f in fixtures if f['fixture_id'] == EXPERIENCE_FIXTURE)
    record = experience_record(exp_ep)
    leaks = find_private_leaks(record, exp_fix['scenario'])
    return {'fixtures': fixtures, 'episodes': episodes, 'probes': probes, 'experience': record,
            'experience_leaks': leaks, 'gates': evaluate_gates(fixtures, episodes, probes, leaks)}


def evaluate_gates(fixtures, episodes, probes, leaks):
    every = [(fid, p, ep) for fid, ps in episodes.items() for p, ep in ps.items()]
    g = {}
    # G1
    init_ok = all(ep['transcript']['initial']['view']['rules'] and ep['transcript']['initial']['view']['state']['day'] == 1
                  and ep['transcript']['initial']['view']['state']['scenario_id'] for _, _, ep in every)
    g['G1'] = {'pass': init_ok, 'evidence': 'Initial observation (state, rules, tools, schema/runtime version, scenario id) recorded per episode in transcripts.json; visibility boundary is enforced by the runner view and tested in test_agent_runner and test_dynamic_demo.'}
    # G2
    clock_ok = True
    for fid, p, ep in every:
        h = ep['history']
        opens = [e['day'] for e in h if e['kind'] == 'day_open']
        closes = [e['day'] for e in h if e['kind'] == 'day_close']
        n = next(f['horizon_days'] for f in fixtures if f['fixture_id'] == fid)
        clock_ok &= opens == list(range(1, n + 1)) == closes and h[-1]['kind'] == 'episode_complete'
    g['G2'] = {'pass': clock_ok, 'evidence': 'Every episode logs day_open then day_close for each day 1..horizon (5 and 15) and ends with episode_complete; see timeline.txt.'}
    # G3
    g3 = True
    for fid, ps in episodes.items():
        sc = next(f for f in fixtures if f['fixture_id'] == fid)['scenario']
        for p, ep in ps.items():
            notice = [e for e in ep['history'] if e['kind'] == 'notice']
            rcpts = {e['details']['order']: e['day'] for e in ep['history'] if e['kind'] == 'receipt'}
            g3 &= len(notice) == 1 and notice[0]['day'] == sc['delay_notice_day']
            if p == 'maintain':
                g3 &= rcpts == {'primary': sc['delayed_arrival_day']}
            if p == 'expedite':
                g3 &= rcpts == {'primary': sc['expedited_arrival_day']}
            if p == 'alternate':
                g3 &= rcpts == {'alternate': sc['alternate_arrival_day'], 'primary': sc['delayed_arrival_day']}
    g['G3'] = {'pass': g3, 'evidence': 'Notice appears on the configured day only; maintain receives the primary PO late, expedite moves the same PO earlier, alternate creates a separate receipt while the original PO still arrives late.'}
    # G4
    g4 = all(ep['report'].feasible and ledger_matches_hand(fid, p, ep['report']) for fid, p, ep in every)
    g['G4'] = {'pass': g4, 'evidence': 'Independent per-day ledger (received, produced, shipped, stock, delivered, penalty, spend) equals the hand-worked ledgers for all 6 episodes and passes conservation checks.'}
    # G5
    g5 = all(scorecard_matches_expected(fid, p, ep['scorecard']) for fid, p, ep in every)
    d5 = all((episodes['s01-five-day'][p]['scorecard']['comparison_cost'], episodes['s01-five-day'][p]['scorecard']['delivered_on_time'],
              episodes['s01-five-day'][p]['scorecard']['ending_components']) == DOC_TABLE_5DAY[p] for p in POLICIES)
    g['G5'] = {'pass': g5 and d5, 'evidence': 'Same initial world and disruption per fixture. The 5-day scorecards equal the acceptance-document tables (cost 120/24/40, on time 4/12/12, ending components 0/0/8). The 15-day results equal separately hand-worked ledgers (200/24/40), which have no document table and no practitioner review.'}
    # G6
    tamper_ok = all(t['rejected_as_expected'] for _, _, ep in every for t in ep['tamper'])
    g['G6'] = {'pass': all(ep['report'].feasible for _, _, ep in every) and tamper_ok,
               'evidence': 'dynamic_verifier re-derives each episode from commands (never imports the simulator; AST test in test_dynamic_verifier). All 6 episodes feasible; 5 corruption cases per episode rejected or ignored as expected (forged scorecard, premature receipt, overproduction, deleted close, forged passed flags).'}
    # G7
    probes_ok = all(p['rejected_count'] >= 2 and p['rejections_left_state_unchanged'] and p['rejections_audited']
                    and p['verifier_feasible'] for p in probes)
    g['G7'] = {'pass': probes_ok, 'partial': True,
               'evidence': 'Demonstrated through the tool interface: hidden-state probe, overcapacity release, duplicate recovery, duplicate release, late recovery, production without material; each rejection leaves state unchanged and stays auditable. Premature receipt, extra receipt, over-budget recovery and beyond-order production are proven at verifier level by unit tests (test_dynamic_verifier), not through the agent tools, because receipts are simulator-driven and the exclusive recovery choices cannot exceed the budget in this fixture.'}
    # G8
    g8 = all(ep['replay']['transcript_reproduced'] and ep['replay']['state_sequence_identical']
             and ep['replay']['replayed_scorecard_identical'] and ep['replay']['replayed_history_feasible'] for _, _, ep in every)
    g['G8'] = {'pass': g8 and not leaks, 'evidence': 'Each transcript replays from recorded calls on a fresh world with identical state sequence and scorecard. One observable experience record (15-day expedite) is published and passes the private-answer scan.'}
    # G9
    g['G9'] = {'pass': None, 'evidence': 'Labels and limitations are published in gate-report.md. Screenshots are attached only if actually captured. Practitioner review has not occurred, so this gate cannot be called passed.'}
    return g
