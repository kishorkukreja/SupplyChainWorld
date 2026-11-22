"""Generators and helpers for the S01 v0.5 property and fuzz tests (issue #19 fixes, finding 1)."""
import json
from pathlib import Path

from hypothesis import strategies as st

from supplychainworld.dynamic_v5 import OperationalWorldV5, ScenarioV5, opaque_label

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.5/scenarios.json').read_text())['fixtures']}
PREMIUMS = st.sampled_from([10, 20, 30, 40, 50, 60])   # base unit cost 10 or 20: every cell is a whole dollar


@st.composite
def _card(draw):
    days = draw(st.lists(st.integers(1, 4), min_size=1, max_size=3, unique=True))
    return [[d, draw(PREMIUMS), d + draw(st.integers(1, 4))] for d in sorted(days)]


@st.composite
def visible_scenarios(draw, warned=None):
    """A valid scenario WITHOUT its outcome fields: (visible dict, horizon, delayed_arrival_day).

    warned=True forces an early-warning signal, False forces none, None lets Hypothesis choose.
    """
    promised = draw(st.integers(4, 7))
    notice = draw(st.integers(2, promised - 1))
    has_signal = draw(st.booleans()) if warned is None else warned
    horizon = draw(st.integers(max(5, promised + 1), 10))
    base = draw(st.sampled_from([10, 20]))
    tiers = [{'tier': 'key', 'weight': draw(st.integers(1, 5)), 'on_shortfall': 'backlog', 'cancel_days_after_due': None}]
    if draw(st.booleans()):
        tiers.append({'tier': 'std', 'weight': 1, 'on_shortfall': 'cancel_after',
                      'cancel_days_after_due': draw(st.integers(0, 3))})
    orders = []
    for i in range(draw(st.integers(1, 2))):
        ptype = draw(st.sampled_from(['percent_of_value', 'fixed_per_unit', 'per_unit_per_day']))
        orders.append({'order_id': f'O{i + 1}', 'tier': draw(st.sampled_from([t['tier'] for t in tiers])),
                       'quantity': draw(st.integers(1, 20)), 'due_day': draw(st.integers(2, horizon)),
                       'unit_value': draw(st.integers(20, 200)), 'penalty_type': ptype,
                       'penalty_rate': draw(st.integers(0, 1000) if ptype == 'percent_of_value' else st.integers(0, 10)),
                       'penalty_cap_pct': draw(st.one_of(st.none(), st.integers(0, 100)))})
    visible = {
        'opening_components': draw(st.integers(0, 8)), 'daily_capacity': draw(st.integers(1, 6)),
        'primary_quantity': draw(st.integers(1, 12)), 'alternate_max_units': draw(st.integers(0, 8)),
        'recovery_budget': draw(st.integers(0, 120)), 'base_unit_cost': base,
        'part_class': draw(st.sampled_from(['standard', 'custom'])),
        'salvage_pct_by_class': {'standard': draw(st.integers(0, 100)), 'custom': draw(st.integers(0, 100))},
        'primary_promised_day': promised, 'notice_day': notice,
        'signal_day': draw(st.integers(1, notice - 1)) if has_signal else None,
        'signal_level': draw(st.sampled_from(['low', 'medium', 'high'])) if has_signal else None,
        'expedite_card': draw(_card()), 'alternate_card': draw(_card()), 'tiers': tiers, 'orders': orders}
    delayed_day = promised + draw(st.integers(1, 4))
    return visible, horizon, delayed_day


def make_scenario(visible, delay, delayed_day):
    """A full v0.5 scenario mapping from a visible part and an outcome."""
    s = dict(visible)
    s['delay_outcome'] = 'delay' if delay else 'none'
    s['delayed_arrival_day'] = delayed_day if delay else None
    s['scenario_id'] = opaque_label(s)
    return s


def world_for(scenario, horizon):
    return OperationalWorldV5(horizon, scenario=ScenarioV5(**scenario))


ACTION_CHOICES = st.one_of(
    st.tuples(st.just('commit_recovery'), st.sampled_from(['expedite', 'alternate']), st.integers(1, 10)),
    st.tuples(st.just('release_production'), st.integers(0, 8)),
    st.tuples(st.just('advance_day')),
    st.tuples(st.just('read_state'), st.sampled_from(['all', 'clock', 'state', 'rules'])),
    st.tuples(st.just('read_recovery_offers')))
action_lists = st.lists(ACTION_CHOICES, max_size=45)


def call_of(action):
    name = action[0]
    if name == 'commit_recovery':
        return {'tool': name, 'arguments': {'choice': action[1], 'quantity': action[2]}}
    if name == 'release_production':
        return {'tool': name, 'arguments': {'quantity': action[1]}}
    if name == 'read_state':
        return {'tool': name, 'arguments': {'section': action[1]}}
    return {'tool': name, 'arguments': {}}


def blind_agent(actions):
    """Plays the listed actions in order whatever it sees, then advances days until the episode is complete."""
    it = iter(actions)

    def agent(view):
        a = next(it, None)
        if a is not None:
            return call_of(a)
        return {'tool': 'advance_day', 'arguments': {}} if view['state']['phase'] != 'complete' else None
    return agent
