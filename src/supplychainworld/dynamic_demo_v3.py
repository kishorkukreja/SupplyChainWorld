"""End-to-end demonstration packet for the S01 v0.3 family (issue #36, round 2).

Runs five declared scripted policies on each of five deterministic scenarios through the observable
tool runner, checks every episode with the independent v0.3 verifier and the hand-worked ledgers,
replays every transcript on a fresh world, scans the one published experience record for private
answers, and reports a PER-METRIC comparison. The comparison never names an overall best policy:
the practitioner asked for cost, service, tier impact, downstream impact and supply risk to be
reported separately, so trade-offs are flagged instead of resolved.

Scripted policies are not LLMs, nothing here measures model ability, and every number is
PROVISIONAL, needs practitioner value. The repair awaits practitioner re-review (reviewed: no, not independent).
"""
import json
from copy import deepcopy
from pathlib import Path

from .agent_runner_v3 import POLICIES_V3, ObservableRunnerV3, replay_v3, scripted_policy_v3
from .dynamic_v3 import OperationalWorldV3, ScenarioV3
from .dynamic_verifier_v3 import check_observations_for_leaks, verify_episode

ROOT = Path(__file__).resolve().parents[2]
EXPERIENCE_FIXTURE, EXPERIENCE_POLICY = 's03-warned-delayed-10d', 'staged_revisit'
EXPERIENCE_SCHEMA = 'dyn36-experience-3'
LEDGER_KEYS = ('received', 'produced', 'shipped', 'components_close', 'finished_close', 'delivered_total',
               'penalty_total', 'spend_total', 'cancelled_total')
# metric id -> (scorecard path, better direction, dimension)
METRICS = {
    'net_cost': (('cost', 'net_cost'), 'lower', 'cost'),
    'recovery_spend': (('cost', 'recovery_spend'), 'lower', 'cost'),
    'expedite_spend': (('cost', 'expedite_spend'), 'lower', 'cost'),
    'alternate_spend': (('cost', 'alternate_spend'), 'lower', 'cost'),
    'service_penalties': (('cost', 'service_penalties'), 'lower', 'cost'),
    'otif_orders_met': (('service', 'otif_orders_met'), 'higher', 'service'),
    'on_time_units': (('service', 'on_time_units'), 'higher', 'service'),
    'unit_days_late': (('service', 'unit_days_late'), 'lower', 'service'),
    'priority_weighted_unit_days_late': (('tier_impact', 'priority_weighted_unit_days_late'), 'lower', 'tier impact'),
    'cancelled_order_value': (('downstream', 'cancelled_order_value'), 'lower', 'downstream impact'),
    'pending_inbound_units': (('supply_risk', 'pending_inbound_units'), 'lower', 'supply risk'),
    'primary_reliance_pct': (('supply_risk', 'primary_reliance_pct'), 'lower', 'supply risk'),
    'ending_cover_days_floor': (('supply_risk', 'ending_cover_days_floor'), 'higher', 'supply risk'),
}
HAND_METRIC_PATHS = {
    'recovery_spend': ('cost', 'recovery_spend'), 'expedite_spend': ('cost', 'expedite_spend'),
    'alternate_spend': ('cost', 'alternate_spend'), 'service_penalties': ('cost', 'service_penalties'),
    'salvage_credit': ('cost', 'salvage_credit'), 'net_cost': ('cost', 'net_cost'),
    'ending_components': ('supply_risk', 'ending_components'), 'otif_orders_met': ('service', 'otif_orders_met'),
    'on_time_units': ('service', 'on_time_units'), 'delivered_total': ('service', 'delivered_total'),
    'cancelled_units': ('service', 'cancelled_units'), 'unit_days_late': ('service', 'unit_days_late'),
    'priority_weighted_unit_days_late': ('tier_impact', 'priority_weighted_unit_days_late'),
    'cancelled_order_value': ('downstream', 'cancelled_order_value'),
    'undelivered_at_end': ('downstream', 'undelivered_at_end'),
    'pending_inbound_units': ('supply_risk', 'pending_inbound_units'),
    'primary_reliance_pct': ('supply_risk', 'primary_reliance_pct'),
    'ending_cover_days_floor': ('supply_risk', 'ending_cover_days_floor'),
    'recovery_commitments': ('supply_risk', 'recovery_commitments'),
    'unused_recovery_budget': ('supply_risk', 'unused_recovery_budget'),
}
FORBIDDEN_KEYS = ('expected', 'oracle', 'answer', 'hidden', 'private', 'reference', 'delay_outcome', 'delayed_arrival_day',
                  'signal_day', 'notice_day', 'opening_components', 'verifier', 'hand_ledger', 'comparison_by_policy')


def load_fixtures(root=ROOT):
    return json.loads((Path(root) / 'fixtures/dynamic/v0.3/scenarios.json').read_text())['fixtures']


def load_hand(root=ROOT):
    return json.loads((Path(root) / 'fixtures/dynamic/v0.3/hand-ledgers.json').read_text())['fixtures']


def factory(fixture, sink=None):
    def make():
        w = OperationalWorldV3(fixture['horizon_days'], scenario=ScenarioV3(**fixture['scenario']))
        if sink is not None:
            sink.append(w)
        return w
    return make


def _get(card, path):
    for k in path:
        card = card[k]
    return card


# ------------------------------------------------------------------ corruption checks

def _alert_index(history):
    return next(i for i, e in enumerate(history)
                if e['kind'] == 'day_open' and (e['state']['signals'] or e['state']['notices']))


def _tamper_checks(fixture, history, scorecard):
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    out = []

    def case(name, hist, card, expect_any):
        r = verify_episode(scenario, hist, horizon_days=horizon, scorecard=card)
        out.append({'case': name, 'feasible': r.feasible, 'codes': r.codes(), 'expected_any_of': sorted(expect_any),
                    'rejected_as_expected': (not r.feasible) and bool(set(expect_any) & set(r.codes()))})

    forged = deepcopy(scorecard)
    forged['cost']['net_cost'] += 17
    case('forged scorecard net cost', history, forged, {'scorecard_mismatch'})
    h = deepcopy(history)
    next(e for e in h if e['kind'] == 'receipt')['day'] -= 1
    case('premature receipt', h, scorecard, {'receipt_timing_or_quantity'})
    h = deepcopy(history)
    close = next(e for e in h if e['kind'] == 'day_close')
    close['state']['penalties'] += 7
    case('wrong penalty claimed', h, scorecard, {'penalty_mismatch'})
    h = deepcopy(history)
    h = [e for e in h if not (e['kind'] == 'day_close' and e['day'] == 2)]
    case('deleted day close', h, scorecard, {'event_day_mismatch', 'missing_event', 'ledger_mismatch'})
    for name, calls, code in (
            ('duplicate commitment (same commit_id executed twice)',
             [{'choice': 'alternate', 'quantity': 1, 'commit_id': 'dup1'}] * 2, 'duplicate_commitment'),
            ('over-budget combined recovery',
             [{'choice': 'expedite', 'quantity': 8, 'commit_id': 'big1'},
              {'choice': 'alternate', 'quantity': 8, 'commit_id': 'big2'}], 'budget_exceeded')):
        h = deepcopy(history)
        i = _alert_index(h)
        for k, d in enumerate(calls):
            h.insert(i + 1 + k, {'day': h[i]['day'], 'kind': 'recovery', 'details': d, 'accepted': True,
                                 'reason': None, 'state': deepcopy(h[i]['state'])})
        case(name, h, scorecard, {code})
    if fixture['scenario']['signal_day'] is not None:
        h = deepcopy(history)
        sig = next(e for e in h if e['kind'] == 'signal')
        sig['details']['delayed_arrival_day'] = fixture['scenario']['delayed_arrival_day']
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

def hand_matches(fixture_id, policy, report, card, hand=None):
    hand = (hand or load_hand())[fixture_id][policy]
    ledger_ok = all([r[k] for r in report.ledger] == hand['ledger'][k] for k in LEDGER_KEYS)
    metrics = {k: _get(card, p) for k, p in HAND_METRIC_PATHS.items()}
    exp = {k: v for k, v in hand['metrics'].items() if k != 'tiers'}
    metrics_ok = all(metrics[k] == v for k, v in exp.items())
    tiers_ok = True
    for tier, want in hand['metrics'].get('tiers', {}).items():
        got = card['tier_impact']['by_tier'][tier]
        tiers_ok &= all(got[k] == v for k, v in want.items())
    return {'ledger': ledger_ok, 'metrics': metrics_ok, 'tiers': tiers_ok}


def run_episode(fixture, policy):
    world = factory(fixture)()
    runner = ObservableRunnerV3(world)
    transcript = runner.run(scripted_policy_v3(policy))
    history, card = world.history(), world.scorecard()
    actions = [{'day': a['day'], 'kind': {'commit_recovery': 'recovery', 'release_production': 'release'}[a['tool']],
                'arguments': a['arguments'], 'result': a['result']}
               for a in transcript['attempts'] if a['tool'] in ('commit_recovery', 'release_production')]
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    report = verify_episode(scenario, history, horizon_days=horizon, scorecard=card, actions=actions)
    sink = []
    ok, diffs = replay_v3(transcript, factory(fixture, sink))
    again = sink[-1]
    rep2 = verify_episode(scenario, again.history(), horizon_days=horizon, scorecard=again.scorecard())
    return {'fixture_id': fixture['fixture_id'], 'policy': policy, 'transcript': transcript, 'history': history,
            'scorecard': card, 'report': report, 'hand': hand_matches(fixture['fixture_id'], policy, report, card),
            'tamper': _tamper_checks(fixture, history, card),
            'replay': {'transcript_reproduced': ok, 'differences': diffs,
                       'state_sequence_identical': again.history() == history,
                       'replayed_scorecard_identical': again.scorecard() == card,
                       'replayed_history_feasible': rep2.feasible}}


# ------------------------------------------------------------------ per-metric comparison

def compare_policies(episodes_for_fixture):
    """Per-metric table for one scenario. Reports which policies are best on each metric alone.

    There is deliberately no overall winner: `best_on_every_metric` lists a policy only if it is
    best (or tied) on all metrics, and `trade_offs` says when different metrics favour different policies.
    """
    table, best_sets = {}, {}
    for m, (path, direction, dim) in METRICS.items():
        vals = {p: _get(ep['scorecard'], path) for p, ep in episodes_for_fixture.items()}
        target = (min if direction == 'lower' else max)(vals.values())
        best = sorted(p for p, v in vals.items() if v == target)
        table[m] = {'dimension': dim, 'better': direction, 'values': vals, 'best_on_this_metric_alone': best}
        best_sets[m] = set(best)
    everywhere = set.intersection(*best_sets.values())
    favoured = {}
    for m, s in best_sets.items():
        for p in s:
            favoured.setdefault(p, []).append(m)
    return {'metrics': table, 'best_on_every_metric': sorted(everywhere),
            'trade_offs': (None if everywhere else
                           'No policy is best on every metric; different metrics favour different policies. '
                           'No overall winner is declared. Weighing cost against service, tier, downstream and '
                           'supply-risk impact is a practitioner decision.'),
            'metrics_favouring_each_policy': {p: sorted(v) for p, v in sorted(favoured.items())}}


# ------------------------------------------------------------------ no-leak evidence

def prefix_before_firm_notice(transcript):
    """What the agent saw and did before any firm notice was visible."""
    return [{'view': {'state': {k: v for k, v in a['view_before']['state'].items() if k != 'scenario_id'},
                      'rules': a['view_before']['rules'],
                      'clock': a['view_before']['clock'], 'last_outcome': a['view_before']['last_outcome']},
             'call': {'tool': a['tool'], 'arguments': a['arguments']}}
            for a in transcript['attempts'] if not a['view_before']['state']['notices']]


def paired_signal_identical(episodes):
    """Warned-and-delayed and warned-and-no-delay must look identical until the firm notice."""
    out = {}
    for p in POLICIES_V3:
        a = prefix_before_firm_notice(episodes['s03-warned-delayed-10d'][p]['transcript'])
        b = prefix_before_firm_notice(episodes['s03-warned-no-delay-10d'][p]['transcript'])
        out[p] = bool(a) and a == b
    return out


def experience_record(episode):
    t = episode['transcript']
    first = t['initial']['view']
    rec = {'schema': EXPERIENCE_SCHEMA, 'scenario_id': t['scenario_id'], 'horizon_days': t['horizon_days'],
           'agent': 'scripted baseline policy (not an LLM; carries no model-ability claim)',
           'values_status': 'PROVISIONAL, needs practitioner value; reviewed: no',
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


# ------------------------------------------------------------------ failure behavior through the tools

def rejection_probes():
    fixture = next(f for f in load_fixtures() if f['fixture_id'] == 's03-sudden-5d')
    runs = {
        'sudden 5d: hidden probe, duplicate action id, over-budget combination, exhausted offers, overcapacity, duplicate release': [
            {'tool': 'read_scenario'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 8}, 'action_id': 'a1'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 8}, 'action_id': 'a1'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 8}, 'action_id': 'a2'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 4}, 'action_id': 'a3'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 1}, 'action_id': 'a4'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 5}, 'action_id': 'a5'},
            {'tool': 'release_production', 'arguments': {'quantity': 9}},
            {'tool': 'release_production', 'arguments': {'quantity': 4}},
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'}],
        'sudden 5d: window closed on day 3, expedite nothing left, production without material': [
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'},
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 2}},
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'}],
    }
    out = []
    for name, calls in runs.items():
        world = factory(fixture)()
        it = iter(calls)
        t = ObservableRunnerV3(world).run(lambda v: next(it, None))
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
    fixtures = load_fixtures()
    episodes = {f['fixture_id']: {p: run_episode(f, p) for p in POLICIES_V3} for f in fixtures}
    probes = rejection_probes()
    exp_fix = next(f for f in fixtures if f['fixture_id'] == EXPERIENCE_FIXTURE)
    record = experience_record(episodes[EXPERIENCE_FIXTURE][EXPERIENCE_POLICY])
    leaks = find_private_leaks(record, exp_fix['scenario'])
    # Scan every episode's observations, not only the published record.
    all_leaks = {}
    for f in fixtures:
        for p in POLICIES_V3:
            t = episodes[f['fixture_id']][p]['transcript']
            obs = [{'state': a['view_before']['state'], 'rules': a['view_before']['rules']} for a in t['attempts']]
            found = check_observations_for_leaks(f['scenario'], obs)
            if found:
                all_leaks[f'{f["fixture_id"]}/{p}'] = found
    comparison = {fid: compare_policies(eps) for fid, eps in episodes.items()}
    pair = paired_signal_identical(episodes)
    packet = {'fixtures': fixtures, 'episodes': episodes, 'probes': probes, 'experience': record,
              'experience_leaks': leaks, 'all_episode_leaks': all_leaks, 'comparison': comparison,
              'paired_signal_identical': pair}
    packet['gates'] = evaluate_gates(packet)
    return packet


def evaluate_gates(packet):
    fixtures, episodes = packet['fixtures'], packet['episodes']
    every = [(fid, p, ep) for fid, ps in episodes.items() for p, ep in ps.items()]
    g = {}
    g['G1'] = {'pass': all(ep['transcript']['initial']['view']['state']['day'] == 1
                           and ep['transcript']['initial']['view']['rules']['orders'] for _, _, ep in every),
               'evidence': 'Initial observation (state, contract terms by order, tier rules, salvage rate, budget, tool definitions, schema/runtime version) recorded per episode in transcripts.json.'}
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
               'evidence': 'Independent per-day ledger equals the hand-worked ledgers for all 25 episodes (received, produced, shipped, stock, delivered, penalties, spend, cancellations) and passes conservation checks.'}
    g['G5'] = {'pass': all(ep['hand']['metrics'] and ep['hand']['tiers'] for _, _, ep in every),
               'evidence': 'Per-metric scorecards (cost, service, tier impact, downstream, supply risk) equal the hand-worked per-episode metrics. Same initial world and disruption per scenario across the five declared policies.'}
    tamper_ok = all(t['rejected_as_expected'] for _, _, ep in every for t in ep['tamper'])
    g['G6'] = {'pass': tamper_ok,
               'evidence': 'dynamic_verifier_v3 re-derives each episode from commands and imports no simulator code (AST test). Corruption cases per episode: forged scorecard, premature receipt, wrong penalty, deleted close, duplicate commitment, over-budget combination, leaked signal (warned scenarios), forged pass flags.'}
    probes_ok = all(p['rejected_count'] >= 3 and p['rejections_left_state_unchanged'] and p['rejections_audited']
                    and p['verifier_feasible'] for p in packet['probes'])
    g['G7'] = {'pass': probes_ok, 'partial': True,
               'evidence': 'Through the tool interface: hidden-state probe, duplicate action id, over-budget combination, overcapacity, duplicate release, closed offer window, exhausted expedite units, production without material. Each rejection leaves state unchanged and stays auditable. Premature receipt, wrong penalty and leaked signals are proven at verifier level.'}
    replay_ok = all(ep['replay']['transcript_reproduced'] and ep['replay']['state_sequence_identical']
                    and ep['replay']['replayed_scorecard_identical'] and ep['replay']['replayed_history_feasible']
                    for _, _, ep in every)
    g['G8'] = {'pass': replay_ok and not packet['experience_leaks'] and not packet['all_episode_leaks']
               and all(packet['paired_signal_identical'].values()),
               'evidence': 'Each transcript replays from recorded calls with identical state sequence and scorecard. All observations in all 25 episodes pass the private-answer and outcome-leak scan; warned-and-delayed and warned-and-no-delay episodes are observation-identical until the firm notice.'}
    g['G9'] = {'pass': None, 'evidence': 'Labels and limitations published. Practitioner re-review has not occurred (reviewed: no); the gate cannot be called passed.'}
    return g
