"""One adapter per S01 version (v0.1 to v0.4) so the same audit tests run on all four.

Only public entry points are used: the scenario and world classes, the observable
runner, `replay*`, the scripted policies and the independent `verify_episode`.
Also holds the Hypothesis strategies that generate scenario parameters (not only
the committed fixtures) and tool-call sequences, and a driver that records a run
while checking caller-supplied invariants after every step.
"""
import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from hypothesis import strategies as st

from supplychainworld import agent_runner as r1, agent_runner_v2 as r2, agent_runner_v3 as r3, agent_runner_v4 as r4
from supplychainworld import dynamic as d1, dynamic_v2 as d2, dynamic_v3 as d3, dynamic_v4 as d4
from supplychainworld import dynamic_verifier as vf1, dynamic_verifier_v2 as vf2
from supplychainworld import dynamic_verifier_v3 as vf3, dynamic_verifier_v4 as vf4

ROOT = Path(__file__).resolve().parents[2]
TAGS = ('v0.1', 'v0.2', 'v0.3', 'v0.4')


def _fixtures(path):
    return json.loads((ROOT / path).read_text())['fixtures']


class Version:
    """Everything the audit tests need to know about one version."""

    def __init__(self, tag, *, scenario_cls, world_cls, runner_cls, replay, scripted, policies, verify,
                 fixtures_path, hidden_keys, leaks=None, multi_commit=False, hand_path=None):
        self.tag, self.scenario_cls, self.world_cls = tag, scenario_cls, world_cls
        self.runner_cls, self._replay, self.scripted, self.policies = runner_cls, replay, scripted, policies
        self._verify, self.fixtures_path, self.hidden_keys = verify, fixtures_path, hidden_keys
        self._leaks, self.multi_commit, self.hand_path = leaks, multi_commit, hand_path

    # ---- construction
    def fixtures(self):
        return _fixtures(self.fixtures_path)

    def world(self, scenario, horizon):
        return self.world_cls(horizon, scenario=self.scenario_cls(**scenario))

    def factory(self, scenario, horizon, sink=None):
        def make():
            w = self.world(scenario, horizon)
            if sink is not None:
                sink.append(w)
            return w
        return make

    def runner(self, scenario, horizon, **kw):
        return self.runner_cls(self.world(scenario, horizon), **kw)

    def scenario_dict(self, world):
        return asdict(world._scenario) if self.tag == 'v0.1' else world._scn.to_dict()

    # ---- verification and replay
    def verify(self, scenario, history, horizon, **kw):
        return self._verify(scenario, history, horizon_days=horizon, **kw)

    def replay(self, transcript, factory):
        return self._replay(transcript, factory)

    def leak_scan(self, scenario, observations):
        return self._leaks(scenario, observations) if self._leaks else []

    # ---- derived data
    @staticmethod
    def actions(transcript):
        kinds = {'commit_recovery': 'recovery', 'release_production': 'release'}
        return [{'day': a['day'], 'kind': kinds[a['tool']], 'arguments': a['arguments'], 'result': a['result']}
                for a in transcript['attempts'] if a['tool'] in kinds]


V1 = Version('v0.1', scenario_cls=d1.SupplierDelayScenario, world_cls=d1.OperationalWorld, runner_cls=r1.ObservableRunner,
             replay=r1.replay, scripted=r1.scripted_policy, policies=('maintain', 'expedite', 'alternate'),
             verify=vf1.verify_episode, fixtures_path='fixtures/dynamic/supplier-delay-inputs.json',
             hidden_keys=('delay_notice_day', 'delayed_arrival_day', 'initially_promised_day', 'recovery_deadline_day',
                          'disruption_enabled', 'opening_components'))
_HID2 = ('delay_outcome', 'delayed_arrival_day', 'signal_day', 'notice_day', 'opening_components')
V2 = Version('v0.2', scenario_cls=d2.ScenarioV2, world_cls=d2.OperationalWorldV2, runner_cls=r2.ObservableRunnerV2,
             replay=r2.replay_v2, scripted=r2.scripted_policy_v2, policies=r2.POLICIES_V2, verify=vf2.verify_episode,
             fixtures_path='fixtures/dynamic/v0.2/scenarios.json', hidden_keys=_HID2,
             leaks=vf2.check_observations_for_leaks, multi_commit=True)
V3 = Version('v0.3', scenario_cls=d3.ScenarioV3, world_cls=d3.OperationalWorldV3, runner_cls=r3.ObservableRunnerV3,
             replay=r3.replay_v3, scripted=r3.scripted_policy_v3, policies=r3.POLICIES_V3, verify=vf3.verify_episode,
             fixtures_path='fixtures/dynamic/v0.3/scenarios.json', hidden_keys=_HID2,
             leaks=vf3.check_observations_for_leaks, multi_commit=True)
V4 = Version('v0.4', scenario_cls=d4.ScenarioV4, world_cls=d4.OperationalWorldV4, runner_cls=r4.ObservableRunnerV4,
             replay=r4.replay_v4, scripted=r4.scripted_policy_v4, policies=r4.POLICIES_V4, verify=vf4.verify_episode,
             fixtures_path='fixtures/dynamic/v0.4/scenarios.json', hidden_keys=_HID2,
             leaks=vf4.check_observations_for_leaks, multi_commit=True)
VERSIONS = {'v0.1': V1, 'v0.2': V2, 'v0.3': V3, 'v0.4': V4}


def fixture_scenario(version, fixture):
    """(scenario dict, horizon) for a fixture of any version; v0.1 fixtures nest the same way."""
    return fixture['scenario'], fixture['horizon_days']


# --------------------------------------------------------------------------- scenario strategies

@st.composite
def v1_scenarios(draw):
    notice = draw(st.integers(1, 4))
    promised = draw(st.integers(notice + 1, notice + 3))
    delayed = draw(st.integers(promised + 1, promised + 4))
    deadline = draw(st.integers(notice, promised - 1))
    expedited = draw(st.integers(deadline + 1, delayed - 1))
    alternate = draw(st.integers(deadline + 1, deadline + 5))
    due = draw(st.integers(1, 8))
    horizon = draw(st.integers(max(due, 1), 14))
    scenario = dict(
        scenario_id='gen-v1', disruption_enabled=draw(st.booleans()), opening_components=draw(st.integers(0, 8)),
        order_quantity=draw(st.integers(1, 20)), daily_capacity=draw(st.integers(1, 6)), order_due_day=due,
        primary_quantity=draw(st.integers(0, 10)), initially_promised_day=promised, delay_notice_day=notice,
        delayed_arrival_day=delayed, recovery_deadline_day=deadline, expedited_arrival_day=expedited,
        alternate_arrival_day=alternate, alternate_quantity=draw(st.integers(0, 10)),
        expedite_cost=draw(st.integers(0, 60)), alternate_cost=draw(st.integers(0, 60)),
        recovery_budget=draw(st.integers(0, 80)), daily_backlog_penalty=draw(st.integers(0, 15)))
    return scenario, horizon


def _curve(draw, unit_cost):
    days = draw(st.lists(st.integers(1, 6), min_size=1, max_size=4, unique=True))
    return [[d, draw(unit_cost), d + draw(st.integers(1, 4))] for d in sorted(days)]


@st.composite
def _core(draw, version):
    """Fields shared by v0.2 to v0.4 generation, drawn so validation passes."""
    notice = draw(st.integers(1, 4))
    promised = draw(st.integers(notice + 1, notice + 4))
    delay = draw(st.booleans())
    warned = notice >= 2 and draw(st.booleans())
    n_orders = draw(st.integers(1, 4))
    tier_names = ['gold', 'std', 'low'][:draw(st.integers(1, 3))]
    orders, tier_due = [], {}
    for i in range(n_orders):
        tier = draw(st.sampled_from(tier_names))
        due = draw(st.integers(1, 9))
        tier_due[tier] = max(tier_due.get(tier, 0), due)
        orders.append({'order_id': f'O{i}', 'tier': tier, 'quantity': draw(st.integers(1, 12)), 'due_day': due,
                       'unit_value': draw(st.integers(0, 50))})
    horizon = draw(st.integers(max(o['due_day'] for o in orders), 14))
    return dict(notice=notice, promised=promised, delay=delay, warned=warned, orders=orders, tier_names=tier_names,
                tier_due=tier_due, horizon=horizon, opening=draw(st.integers(0, 8)), capacity=draw(st.integers(1, 6)),
                primary=draw(st.integers(0, 10)), alt_max=draw(st.integers(0, 10)), budget=draw(st.integers(0, 80)),
                delayed=promised + draw(st.integers(1, 5)))


@st.composite
def v2_scenarios(draw):
    c = draw(_core('v2'))
    cancel_extra = {t: draw(st.integers(0, 4)) for t in c['tier_names']}
    tiers = []
    for t in c['tier_names']:
        cancel = draw(st.booleans())
        tiers.append({'tier': t, 'weight': draw(st.integers(1, 5)),
                      'on_shortfall': 'cancel_after' if cancel else 'backlog',
                      'cancel_day': (c['tier_due'][t] + cancel_extra[t]) if cancel and t in c['tier_due'] else
                      (draw(st.integers(1, 10)) if cancel else None)})
    orders = []
    for o in c['orders']:
        ptype = draw(st.sampled_from(d2.PENALTY_TYPES))
        orders.append({**o, 'penalty_type': ptype,
                       'penalty_rate': draw(st.integers(0, 100 if ptype == 'percent_of_value' else 15))})
    cost = st.integers(0, 8)
    scenario = dict(
        scenario_id='gen-v2', opening_components=c['opening'], daily_capacity=c['capacity'], primary_quantity=c['primary'],
        primary_promised_day=c['promised'], signal_day=draw(st.integers(1, c['notice'] - 1)) if c['warned'] else None,
        notice_day=c['notice'], delay_outcome='delay' if c['delay'] else 'none',
        delayed_arrival_day=c['delayed'] if c['delay'] else None, expedite_curve=_curve(draw, cost),
        alternate_curve=_curve(draw, cost), alternate_max_units=c['alt_max'], recovery_budget=c['budget'],
        salvage_per_component=draw(st.integers(0, 6)), tiers=tiers, orders=orders)
    scenario['signal_hint_pct'] = draw(st.integers(0, 100)) if c['warned'] else None
    return scenario, c['horizon']


@st.composite
def v3_scenarios(draw):
    c = draw(_core('v3'))
    tiers = []
    for t in c['tier_names']:
        cancel = draw(st.booleans())
        tiers.append({'tier': t, 'weight': draw(st.integers(1, 5)),
                      'on_shortfall': 'cancel_after' if cancel else 'backlog',
                      'cancel_days_after_due': draw(st.integers(0, 5)) if cancel else None})
    orders = []
    for o in c['orders']:
        ptype = draw(st.sampled_from(d3.PENALTY_TYPES))
        orders.append({**o, 'penalty_type': ptype,
                       'penalty_rate': draw(st.integers(0, 500 if ptype == 'percent_of_value' else 15)),
                       'penalty_cap_pct': draw(st.one_of(st.none(), st.integers(0, 100)))})
    base = draw(st.sampled_from([10, 20, 50, 100]))

    def card():
        days = draw(st.lists(st.integers(1, 6), min_size=1, max_size=4, unique=True))
        return [[d, 10 * draw(st.integers(1, 15)), d + draw(st.integers(1, 4))] for d in sorted(days)]
    scenario = dict(
        scenario_id='gen-v3', opening_components=c['opening'], daily_capacity=c['capacity'], primary_quantity=c['primary'],
        primary_promised_day=c['promised'], signal_day=draw(st.integers(1, c['notice'] - 1)) if c['warned'] else None,
        signal_level=draw(st.sampled_from(d3.SIGNAL_LEVELS)) if c['warned'] else None,
        notice_day=c['notice'], delay_outcome='delay' if c['delay'] else 'none',
        delayed_arrival_day=c['delayed'] if c['delay'] else None, base_unit_cost=base, expedite_card=card(),
        alternate_card=card(), alternate_max_units=c['alt_max'], recovery_budget=c['budget'],
        part_class=draw(st.sampled_from(d3.PART_CLASSES)),
        salvage_pct_by_class={'standard': draw(st.integers(0, 100)), 'custom': draw(st.integers(0, 100))},
        tiers=tiers, orders=orders)
    return scenario, c['horizon']


SCENARIO_STRATEGIES = {'v0.1': v1_scenarios(), 'v0.2': v2_scenarios(), 'v0.3': v3_scenarios(), 'v0.4': v3_scenarios()}


def fixture_or_generated(version):
    """Half committed fixtures, half generated scenarios (so fixtures stay in the property mix)."""
    fx = [fixture_scenario(version, f) for f in version.fixtures()]
    return st.one_of(st.sampled_from(fx), SCENARIO_STRATEGIES[version.tag])


# --------------------------------------------------------------------------- tool-call generation

def informed_call(version, view, data):
    """Draw one tool call, biased toward calls the current view says could be legal.

    Uses only the agent-visible view. Many calls are still rejected; that is intended.
    """
    kind = data.draw(st.sampled_from(['advance', 'advance', 'release', 'release', 'commit', 'commit', 'read']))
    rules = view['rules']
    if kind == 'advance':
        return {'tool': 'advance_day', 'arguments': {}}
    if kind == 'read':
        return data.draw(st.sampled_from([{'tool': 'read_state', 'arguments': {}},
                                          {'tool': 'read_state', 'arguments': {'section': 'rules'}},
                                          {'tool': 'read_recovery_offers', 'arguments': {}}]))
    if kind == 'release':
        cap = rules['capacity']
        return {'tool': 'release_production', 'arguments': {'quantity': data.draw(st.integers(-1, cap + 1))}}
    if not version.multi_commit:
        return {'tool': 'commit_recovery',
                'arguments': {'choice': data.draw(st.sampled_from(['maintain', 'expedite', 'alternate']))}}
    offers = rules.get('recovery_offers')
    choice = data.draw(st.sampled_from(['expedite', 'alternate']))
    today = (offers or {}).get(choice, {}).get('today') if offers else None
    top = today['max_units'] + 1 if today else 3
    call = {'tool': 'commit_recovery', 'arguments': {'choice': choice, 'quantity': data.draw(st.integers(0, top))}}
    if data.draw(st.booleans()):
        call['action_id'] = f"a{view['state']['day']}-{len(view['state']['commitments'])}-{data.draw(st.integers(0, 3))}"
    return call


def greedy_release(view):
    """The scripted policies' production rule, from the visible view only (works for every version)."""
    s, r = view['state'], view['rules']
    demand = r['required'] - s['produced_total'] if 'required' in r else max(0, s['open_demand'] - s['finished_on_hand'])
    return max(0, min(r['capacity'], s['component_on_hand'], demand))


def drive(version, scenario, horizon, data, *, steps=24, check=None, runner_kw=None):
    """Run one episode with generated calls, then close all days. Returns (transcript, runner).

    `check(world, record_or_None)` runs before the first call and after every attempt.
    The recorded run is a normal runner transcript, so it can be replayed and verified.
    """
    runner = version.runner(scenario, horizon, **(runner_kw or {}))
    state = {'n': 0}

    def agent(view):
        if check and runner._attempts:
            check(runner._world, runner._attempts[-1])
        state['n'] += 1
        if state['n'] > steps:
            return {'tool': 'advance_day', 'arguments': {}}
        return informed_call(version, view, data)

    transcript = runner.run(agent)
    if check:
        check(runner._world, runner._attempts[-1] if runner._attempts else None)
    return transcript, runner


def scripted_transcript(version, scenario, horizon, policy):
    runner = version.runner(scenario, horizon)
    return runner.run(version.scripted(policy)), runner


def strip(obj):
    return json.loads(json.dumps(obj))


def deep(obj):
    return deepcopy(obj)
