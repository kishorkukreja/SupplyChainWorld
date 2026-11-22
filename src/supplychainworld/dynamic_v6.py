"""Deterministic operational kernel for the S01 v0.6 scenario family (issue #19, audit follow-up).

Built beside `dynamic_v5.py` (and v0.1 to v0.5), all untouched; v0.5 is reused by subclassing. Every business
rule and every number is the v0.5 (= v0.4) rule and number: all PROVISIONAL, needs practitioner value; not
reviewed by a practitioner. What is new in v0.6:

1. CONVENTIONS BLOCK (audit finding F6, S01.3). The agent-visible `rules` now carry a `conventions` block that
   states, from the world itself, the rules an assessor needs to turn the visible numbers into outcomes: whether a
   receipt that arrives at day opening can be used in the same day's production, when production completes, when
   shipping starts, in what order due orders are served, how penalties are assessed and in which unit the penalty
   rate is written, and how cancellation works. `statements` are plain sentences, `parameters` are the same facts
   as machine-readable values; a test ties the two together and a test ties the parameters to the independent
   checker. The early-warning boundary is unchanged: the block depends only on visible parameters, so twin
   scenarios that differ in the hidden outcome still show identical observations until the firm notice.

2. EXACT-ONCE WITHOUT AN ACTION ID (audit finding F4, S01.4). In v0.2 to v0.5 a recovery was exact-once only if the
   caller supplied an `action_id` (a re-sent call without one was a second purchase). In v0.6 a commitment made
   WITHOUT an id gets a deterministic key derived from its content and day, `auto-` plus 8 hex characters of
   SHA-256 of `day|choice|quantity`, and is refused when that key is already used or when an identical purchase
   (same day, choice and quantity) was already made today under any id. Identical purchases that are meant (two
   lots of the same size on one day) need distinct explicit ids. The `auto-` prefix is reserved: an explicit id
   that starts with it is refused. The alternative (rejecting a missing id) was not chosen because the scripted
   baselines and the first diagnostic harness never send ids, and refusing them would change what those runs do.

Schema and runtime version are `6.0`; the scenario id rule (opaque label of the visible parameters) is v0.5's.
"""
import hashlib
from copy import deepcopy

from .dynamic_v3 import SIGNAL_TEXT, _tier  # noqa: F401
from .dynamic_v5 import LABEL_PATTERN, OperationalWorldV5, ScenarioV5, opaque_label  # noqa: F401

SCHEMA = '6.0'
VALUES_STATUS = 'PROVISIONAL, needs practitioner value; not reviewed by a practitioner'
SCORECARD_SCHEMA = 'dyn-scorecard-6'
AUTO_PREFIX = 'auto-'

# One plain sentence per convention. Written for the agent; no outcome-class wording (the leak scan reads it).
CONVENTION_STATEMENTS = {
    'day_sequence': ('Each day has three steps: at day opening lots arrive and any signal or notice appears; then you '
                     'act (commit recovery, release production); then advance_day closes the day, in this order: '
                     'production completes, goods ship, penalties and cancellations are assessed.'),
    'receipts_usable_on_arrival_day': ('A lot whose arrival_day is today has already arrived when you act: its units '
                                       'are in component_on_hand at day opening and a release made today can use them.'),
    'production_completes_at': ('A release made today is built at the close of today: the components leave '
                                'component_on_hand and the finished goods enter finished_on_hand at that close, before '
                                'shipping, so they can ship at the same close.'),
    'shipping_starts_on': ('An order is shipped only from the close of its due_day on, and at every close after that '
                           'while it is still open; goods are never shipped before the due day, even if they are on hand.'),
    'shipping_priority': ('At each close the due orders are served in this sequence: highest tier weight first, then '
                          'order_id in ascending text order; each takes the smaller of the finished goods still on '
                          'hand and its undelivered units.'),
    'on_time_units': ('on_time_units of an order are the units delivered by the close of its due_day; units shipped '
                      'later are delivered but not on time.'),
    'penalty_assessed_at': ('A penalty is assessed at each close for every open order whose due_day is today or '
                            'earlier and that still has undelivered units after that close\'s shipping; each daily '
                            'amount is rounded down to whole USD.'),
    'penalty_rate_unit_percent_of_value': ('For penalty_type percent_of_value, penalty_rate is in basis points (one '
                                           'hundredth of one percent, so 150 means 1.5 percent): each late day costs '
                                           'undelivered units x unit_value x penalty_rate / 10000.'),
    'penalty_rate_unit_fixed_per_unit': ('For penalty_type fixed_per_unit, penalty_rate is whole USD per undelivered '
                                         'unit, charged once, at the close of the due_day only.'),
    'penalty_rate_unit_per_unit_per_day': ('For penalty_type per_unit_per_day, penalty_rate is whole USD per '
                                           'undelivered unit for each day the order is still short, from its due_day on.'),
    'penalty_cap': ('penalty_cap_pct, when not null, is a whole percent of the full order value (quantity x '
                    'unit_value): the penalties of one order add up to at most that; null means no cap.'),
    'cancellation': ('A cancel_after tier cancels the undelivered units of an order at the close of the day '
                     'due_day + cancel_days_after_due, after that day\'s shipping and penalty; cancelled units are '
                     'never delivered and cost no further penalty; a backlog tier never cancels.'),
    'lot_timing': ('A lot arrives at the opening of its arrival_day. An expedited lot takes the arrival_day of the '
                   'offer; a lot bought from the alternate supplier arrives on the arrival_day of the offer row for '
                   'the day it was bought; the primary lot keeps its shown arrival_day unless a firm notice changes it.'),
    'repeated_purchase': ('A commit_recovery sent without an action_id is given a key built from the day, the '
                          'choice and the quantity: the same purchase repeated on the same day without a distinct '
                          'action_id is refused, and the prefix auto- is reserved. Send distinct action_ids to buy '
                          'identical lots on purpose.'),
    'before_a_firm_notice': ('Until a firm notice is shown, a lot shows its promised arrival_day and a possible-delay '
                             'signal gives only a level: what you see then is a plan, not a promise.'),
}
CONVENTION_PARAMETERS = {
    'receipts_usable_on_arrival_day': True,
    'production_completes_at': 'day_close',
    'shipping_starts_on': 'order_due_day',
    'shipping_priority': 'tier_weight_descending_then_order_id_ascending',
    'penalty_rate_divisor_percent_of_value': 10000,
    'penalty_rate_unit_percent_of_value': 'basis_points',
    'penalty_rate_unit_fixed_per_unit': 'usd_per_undelivered_unit_charged_once_on_due_day',
    'penalty_rate_unit_per_unit_per_day': 'usd_per_undelivered_unit_per_day_from_due_day',
    'penalty_rounding': 'down_to_whole_usd_each_day_per_order',
    'penalty_cap_basis': 'percent_of_order_value',
    'cancellation_day': 'due_day_plus_cancel_days_after_due',
    'on_time_means': 'delivered_by_close_of_due_day',
    'auto_key_prefix': AUTO_PREFIX,
}


def conventions_block():
    """A fresh copy of the block shown to the agent under `rules['conventions']`."""
    return {'statements': dict(CONVENTION_STATEMENTS), 'parameters': deepcopy(CONVENTION_PARAMETERS)}


def derived_commit_key(day, choice, quantity):
    """Deterministic key for a commitment sent without an action id."""
    return AUTO_PREFIX + hashlib.sha256(f'{day}|{choice}|{quantity}'.encode()).hexdigest()[:8]


class ScenarioV6(ScenarioV5):
    """v0.5 scenario fields and validation (opaque label rule included); only the version differs."""

    def __init__(self, **kw):
        if kw.get('schema_version', SCHEMA) != SCHEMA or kw.get('runtime_version', SCHEMA) != SCHEMA:
            raise ValueError('unsupported scenario or runtime version')
        kw = {k: v for k, v in kw.items() if k not in ('schema_version', 'runtime_version')}
        super().__init__(**kw)
        self.schema_version = self.runtime_version = SCHEMA


class OperationalWorldV6(OperationalWorldV5):
    """v0.5 world, same rules and numbers, plus the conventions block and exact-once without an action id."""

    def __init__(self, horizon_days: int = 5, *, scenario: ScenarioV6):
        if not isinstance(scenario, ScenarioV6):
            raise TypeError('scenario must be a ScenarioV6')
        super().__init__(horizon_days, scenario=scenario)

    def snapshot(self):
        s = super().snapshot()
        s['schema_version'] = s['runtime_version'] = SCHEMA
        return s

    def observation(self):
        obs = super().observation()
        obs['rules']['conventions'] = conventions_block()
        return obs

    def choose_recovery(self, choice, quantity=None, commit_id=None):
        s = self._s
        valid_shape = (s['phase'] == 'action' and self._alert_visible() and choice in ('expedite', 'alternate')
                       and type(quantity) is int and quantity >= 1)
        if valid_shape and commit_id is not None and isinstance(commit_id, str) and commit_id.startswith(AUTO_PREFIX):
            return self._reject('recovery', {'choice': choice, 'quantity': quantity, 'commit_id': commit_id},
                                'duplicate commitment: the action_id prefix auto- is reserved')
        if valid_shape and commit_id is None:
            key = derived_commit_key(s['day'], choice, quantity)
            same = any(c['day'] == s['day'] and c['choice'] == choice and c['quantity'] == quantity
                       for c in s['commitments'])
            if same or key in {c['commit_id'] for c in s['commitments']}:
                return self._reject('recovery', {'choice': choice, 'quantity': quantity, 'commit_id': None},
                                    'duplicate commitment: the same purchase was already made today')
            return super().choose_recovery(choice, quantity, key)
        return super().choose_recovery(choice, quantity, commit_id)

    def scorecard(self):
        card = super().scorecard()
        card['schema'] = SCORECARD_SCHEMA
        return card
