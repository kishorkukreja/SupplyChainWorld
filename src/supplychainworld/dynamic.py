"""Deterministic operational kernel for the proposed S01 supplier-delay fixture.

This is a deliberately narrow engineering model, not a general ERP or a
practitioner-validated supply-chain simulator. Quantities are indivisible units.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Literal

Recovery = Literal['maintain', 'expedite', 'alternate']


@dataclass(frozen=True)
class SupplierDelayScenario:
    """Scenario mechanics. This object contains hidden future events.

    Keep it inside the environment; provide only `observation()` to a policy.
    Values are whole units, simulation-day indices and whole USD respectively.
    """
    scenario_id: str = 's01-five-day'
    schema_version: str = '1.0'
    runtime_version: str = '1.0'
    disruption_enabled: bool = True
    opening_components: int = 4
    order_quantity: int = 12
    daily_capacity: int = 4
    order_due_day: int = 3
    primary_quantity: int = 8
    initially_promised_day: int = 2
    delay_notice_day: int = 1
    delayed_arrival_day: int = 4
    recovery_deadline_day: int = 1
    expedited_arrival_day: int = 2
    alternate_arrival_day: int = 2
    alternate_quantity: int = 8
    expedite_cost: int = 24
    alternate_cost: int = 40
    recovery_budget: int = 40
    daily_backlog_penalty: int = 10

    def __post_init__(self):
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError('scenario_id must be a nonempty string')
        if self.schema_version != '1.0' or self.runtime_version != '1.0':
            raise ValueError('unsupported scenario or runtime version')
        if type(self.disruption_enabled) is not bool:
            raise ValueError('disruption_enabled must be boolean')
        quantities = ('opening_components', 'order_quantity', 'daily_capacity',
                      'primary_quantity', 'alternate_quantity', 'expedite_cost',
                      'alternate_cost', 'recovery_budget', 'daily_backlog_penalty')
        for key in quantities:
            value = getattr(self, key)
            if type(value) is not int or value < 0:
                raise ValueError(f'{key} must be a nonnegative integer')
        for key in ('order_due_day', 'initially_promised_day', 'delay_notice_day',
                    'delayed_arrival_day', 'recovery_deadline_day',
                    'expedited_arrival_day', 'alternate_arrival_day'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(f'{key} must be a positive integer')
        if not self.delay_notice_day < self.initially_promised_day < self.delayed_arrival_day:
            raise ValueError('notice must precede the promised arrival, which must precede delay')
        if not self.delay_notice_day <= self.recovery_deadline_day < self.initially_promised_day:
            raise ValueError('recovery deadline must follow notice and precede original arrival')
        if not self.recovery_deadline_day < self.expedited_arrival_day < self.delayed_arrival_day:
            raise ValueError('expedited arrival must follow the deadline and precede delayed arrival')
        if not self.recovery_deadline_day < self.alternate_arrival_day:
            raise ValueError('alternate arrival must follow the recovery deadline')


@dataclass
class State:
    schema_version: str = '1.0'
    runtime_version: str = '1.0'
    scenario_id: str = 's01-five-day'
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

    def __init__(self, horizon_days: int = 5, *, scenario: SupplierDelayScenario | None = None):
        if type(horizon_days) is not int or horizon_days < 1:
            raise ValueError('horizon_days must be a positive integer')
        if scenario is not None and not isinstance(scenario, SupplierDelayScenario):
            raise TypeError('scenario must be a SupplierDelayScenario')
        self._scenario = scenario or SupplierDelayScenario()
        self._horizon_days = horizon_days
        # These are public business facts, retained for backwards compatibility.
        self.capacity = self._scenario.daily_capacity
        self.required = self._scenario.order_quantity
        self.primary_quantity = self._scenario.primary_quantity
        self.alternate_quantity = self._scenario.alternate_quantity
        self.recovery_budget = self._scenario.recovery_budget
        self.reset()

    def reset(self):
        self._state = State(schema_version=self._scenario.schema_version,
                            runtime_version=self._scenario.runtime_version,
                            scenario_id=self._scenario.scenario_id,
                            horizon_days=self._horizon_days,
                            component_on_hand=self._scenario.opening_components,
                            primary_arrival_day=self._scenario.initially_promised_day)
        self._history = []
        self._open_day()
        return self.snapshot()

    def snapshot(self):
        return deepcopy(asdict(self._state))

    def observation(self):
        """Visible current state and decision rules, excluding future event plan."""
        rules = {'capacity': self.capacity, 'required': self.required,
                 'due_day': self._scenario.order_due_day, 'recovery_budget': self.recovery_budget,
                 'daily_backlog_penalty': self._scenario.daily_backlog_penalty}
        if self._state.notices:
            rules['recovery_offers'] = {
                'deadline_day': self._scenario.recovery_deadline_day,
                'expedite_cost': self._scenario.expedite_cost,
                'expedited_arrival_day': self._scenario.expedited_arrival_day,
                'alternate_cost': self._scenario.alternate_cost,
                'alternate_arrival_day': self._scenario.alternate_arrival_day,
                'alternate_quantity': self.alternate_quantity}
        return {'state': self.snapshot(), 'rules': rules}

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
        if s.phase != 'action' or not s.notices or s.day > self._scenario.recovery_deadline_day:
            return self._reject('recovery', d, 'recovery unavailable or deadline has passed')
        if s.recovery is not None:
            return self._reject('recovery', d, 'recovery already committed')
        if choice not in ('maintain', 'expedite', 'alternate'):
            return self._reject('recovery', d, 'unknown recovery option')
        spend = {'maintain': 0, 'expedite': self._scenario.expedite_cost,
                 'alternate': self._scenario.alternate_cost}[choice]
        if s.incremental_spend + spend > self.recovery_budget:
            return self._reject('recovery', d, 'recovery budget exceeded')
        s.recovery = choice
        s.incremental_spend += spend
        if choice == 'expedite':
            s.primary_arrival_day = self._scenario.expedited_arrival_day
        elif choice == 'alternate':
            s.alternate_arrival_day = self._scenario.alternate_arrival_day
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
        if s.day >= self._scenario.order_due_day:
            shipped = min(s.finished_on_hand, self.required - s.delivered_total)
            s.finished_on_hand -= shipped
            s.delivered_total += shipped
            s.penalties += self._scenario.daily_backlog_penalty * (self.required - s.delivered_total)
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
        # This internal event records opening state before any same-day notice.
        self._record('opening_before_notice', {}, True)
        if self._scenario.disruption_enabled and s.day == self._scenario.delay_notice_day:
            original = self._scenario.initially_promised_day
            revised = self._scenario.delayed_arrival_day
            s.primary_arrival_day = revised
            s.notices.append(f'Primary PO delayed from day {original} to day {revised}')
            self._record('notice', {'original_day': original, 'revised_day': revised}, True)
        self._record('day_open', {}, True)

    def scorecard(self):
        s = self._state
        if s.phase != 'complete':
            raise ValueError('scorecard requires completed episode')
        due_close = next((e for e in self._history if e['kind'] == 'day_close' and e['day'] == self._scenario.order_due_day), None)
        return {'delivered_on_time': due_close['state']['delivered_total'] if due_close else None,
                'delivered_total': s.delivered_total, 'ending_components': s.component_on_hand,
                'incremental_spend': s.incremental_spend, 'service_penalties': s.penalties,
                'comparison_cost': s.incremental_spend + s.penalties}
