"""Deterministic operational kernel for the proposed S01 supplier-delay fixture.

This is a deliberately narrow engineering model, not a general ERP or a
practitioner-validated supply-chain simulator. Quantities are indivisible units.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Literal

Recovery = Literal['maintain', 'expedite', 'alternate']


@dataclass
class State:
    day: int = 1
    horizon_days: int = 5
    phase: str = 'action'
    component_on_hand: int = 4
    finished_on_hand: int = 0
    produced_total: int = 0
    delivered_total: int = 0
    primary_arrival_day: int = 4
    primary_received: bool = False
    alternate_arrival_day: int | None = None
    alternate_received: bool = False
    recovery: str | None = None
    incremental_spend: int = 0
    penalties: int = 0
    scheduled_production: int | None = None
    notices: list[str] = field(default_factory=list)


class OperationalWorld:
    """S01 world: one factory, one component and one 12-unit order.

    Instances own their state. `snapshot` and `history` return detached copies.
    Rejected commands are recorded without mutating operational state.
    """
    capacity = 4
    required = 12
    primary_quantity = 8
    alternate_quantity = 8
    recovery_budget = 40

    def __init__(self, horizon_days: int = 5):
        if type(horizon_days) is not int or horizon_days < 1:
            raise ValueError('horizon_days must be a positive integer')
        self._horizon_days = horizon_days
        self.reset()

    def reset(self):
        self._state = State(horizon_days=self._horizon_days)
        self._history = []
        # Opening day 1: the initially promised day-2 order is delayed to day 4.
        self._state.notices.append('Primary PO delayed from day 2 to day 4')
        self._record('notice', {'original_day': 2, 'revised_day': 4}, True)
        return self.snapshot()

    def snapshot(self):
        return deepcopy(asdict(self._state))

    def history(self):
        return deepcopy(self._history)

    def _record(self, kind, details, accepted, reason=None):
        self._history.append({'day': self._state.day, 'kind': kind,
                              'details': deepcopy(details), 'accepted': accepted,
                              'reason': reason, 'state': self.snapshot()})

    def _reject(self, kind, details, reason):
        self._record(kind, details, False, reason)
        return {'accepted': False, 'reason': reason}

    def choose_recovery(self, choice: Recovery):
        d = {'choice': choice}
        s = self._state
        if s.phase != 'action' or s.day != 1:
            return self._reject('recovery', d, 'recovery deadline has passed')
        if s.recovery is not None:
            return self._reject('recovery', d, 'recovery already committed')
        if choice not in ('maintain', 'expedite', 'alternate'):
            return self._reject('recovery', d, 'unknown recovery option')
        spend = {'maintain': 0, 'expedite': 24, 'alternate': 40}[choice]
        if s.incremental_spend + spend > self.recovery_budget:
            return self._reject('recovery', d, 'recovery budget exceeded')
        s.recovery = choice
        s.incremental_spend += spend
        if choice == 'expedite':
            s.primary_arrival_day = 2
        elif choice == 'alternate':
            s.alternate_arrival_day = 2
        self._record('recovery', d, True)
        return {'accepted': True}

    def release_production(self, quantity: int):
        d = {'quantity': quantity}
        s = self._state
        if s.phase != 'action':
            return self._reject('release', d, 'episode is closed')
        if s.scheduled_production is not None:
            return self._reject('release', d, 'daily production already released')
        if type(quantity) is not int or quantity < 0:
            return self._reject('release', d, 'quantity must be a nonnegative integer')
        if quantity > self.capacity or quantity > s.component_on_hand:
            return self._reject('release', d, 'capacity or available material exceeded')
        if s.produced_total + quantity > self.required:
            return self._reject('release', d, 'production exceeds customer requirement')
        s.scheduled_production = quantity
        self._record('release', d, True)
        return {'accepted': True}

    def close_day(self):
        s = self._state
        if s.phase != 'action':
            return self._reject('close_day', {}, 'episode is closed')
        quantity = s.scheduled_production or 0
        s.component_on_hand -= quantity
        s.finished_on_hand += quantity
        s.produced_total += quantity
        s.scheduled_production = None
        shipped = 0
        if s.day >= 3:
            shipped = min(s.finished_on_hand, self.required - s.delivered_total)
            s.finished_on_hand -= shipped
            s.delivered_total += shipped
            s.penalties += 10 * (self.required - s.delivered_total)
        self._record('day_close', {'produced': quantity, 'shipped': shipped}, True)
        if s.day == self._horizon_days:
            s.phase = 'complete'
            self._record('episode_complete', {'comparison_cost': s.incremental_spend + s.penalties}, True)
            return self.snapshot()
        s.day += 1
        self._open_day()
        return self.snapshot()

    def _open_day(self):
        s = self._state
        if not s.primary_received and s.primary_arrival_day == s.day:
            s.primary_received = True
            s.component_on_hand += self.primary_quantity
            self._record('receipt', {'order': 'primary', 'quantity': self.primary_quantity}, True)
        if not s.alternate_received and s.alternate_arrival_day == s.day:
            s.alternate_received = True
            s.component_on_hand += self.alternate_quantity
            self._record('receipt', {'order': 'alternate', 'quantity': self.alternate_quantity}, True)
        self._record('day_open', {}, True)

    def scorecard(self):
        s = self._state
        if s.phase != 'complete':
            raise ValueError('scorecard requires completed episode')
        close3 = next((e for e in self._history if e['kind'] == 'day_close' and e['day'] == 3), None)
        return {'delivered_on_time': close3['state']['delivered_total'] if close3 else None,
                'delivered_total': s.delivered_total, 'ending_components': s.component_on_hand,
                'incremental_spend': s.incremental_spend, 'service_penalties': s.penalties,
                'comparison_cost': s.incremental_spend + s.penalties}
