"""Static supplier-allocation contracts, schema/rules version 1.2 (owner-practitioner re-review, issue #35).

Lives beside the frozen 1.0 (``schemas.py``) and 1.1 (``schemas_v11.py``) contracts; nothing there changes.
Every numeric policy value a fixture sets is PROVISIONAL, needs practitioner value. The re-review answers
are not independent. See docs/acceptance/static-v1.2-provisional-values.md.
"""
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, TypeAdapter, model_validator

from . import schemas_v11 as v11
from .schemas import Identifier, Money, Quantity

VERSION = '1.2'

# Fixed z-table for the target service level (one-sided normal quantile, four decimals). PROVISIONAL.
# Fixed constants keep the safety stock exact and deterministic: no float, no library quantile.
Z_TABLE: dict[Decimal, Decimal] = {
    Decimal('0.90'): Decimal('1.2816'),
    Decimal('0.95'): Decimal('1.6449'),
    Decimal('0.975'): Decimal('1.9600'),
    Decimal('0.99'): Decimal('2.3263'),
}


def _ratio(value: Decimal | None, name: str):
    if value is not None and value > 1:
        raise ValueError(f'{name} must be in [0,1]')


class Contract12(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    schema_version: Literal['1.2'] = '1.2'


class Item(Contract12):
    """C1: safety stock = ceil(z(service_level) x demand_std x sqrt(lead_time_periods)), exact, or an explicit override."""
    item_id: Identifier
    unit: Literal['each'] = 'each'
    demand: Quantity
    due_date: date
    excess_allowance: Quantity = 0
    service_level: Money | None = None          # one of Z_TABLE keys (0.90, 0.95, 0.975, 0.99)
    demand_std: Money | None = None             # per-period demand standard deviation, units
    lead_time_periods: Money | None = None      # replenishment lead time in the same periods as demand_std
    safety_stock_override: Quantity | None = None  # explicit override of the computed value
    critical: StrictBool = False
    moq_excess_allowed: StrictBool = False
    max_excess: Quantity | None = None

    @model_validator(mode='after')
    def safety_inputs(self):
        given = [self.service_level, self.demand_std, self.lead_time_periods]
        if any(v is not None for v in given) and any(v is None for v in given):
            raise ValueError('service_level, demand_std and lead_time_periods are declared together or not at all')
        if self.service_level is not None and self.service_level not in Z_TABLE:
            raise ValueError('service_level must be one of 0.90, 0.95, 0.975, 0.99')
        return self


class Stock(v11.Stock):
    schema_version: Literal['1.2'] = '1.2'


class Inbound(v11.Inbound):
    schema_version: Literal['1.2'] = '1.2'


class FixedChargeTier(v11.FixedChargeTier):
    schema_version: Literal['1.2'] = '1.2'


class Supplier(v11.Supplier):
    schema_version: Literal['1.2'] = '1.2'
    fixed_charge_table: list[FixedChargeTier] = Field(default_factory=list)


class Quote(v11.Quote):
    schema_version: Literal['1.2'] = '1.2'


class ConcentrationRule(Contract12):
    """C7: spend_share is the default measure. quantity_share and per_item_share only when the task declares them."""
    measure: Literal['spend_share', 'quantity_share', 'per_item_share'] = 'spend_share'
    limit: Money
    item_ids: list[Identifier] | None = None

    @model_validator(mode='after')
    def scope(self):
        _ratio(self.limit, 'limit')
        if self.measure == 'spend_share' and self.item_ids is not None:
            raise ValueError('spend_share covers all spend; item_ids must be omitted')
        if self.measure == 'quantity_share' and not self.item_ids:
            raise ValueError('quantity_share must name the items whose units are summed')
        return self


class Constraints(Contract12):
    budget: Money
    concentration: list[ConcentrationRule] = Field(default_factory=list)
    approval_limit: Money | None = None  # C4: an estimate is allowed when the line value is AT OR BELOW this


class ToleranceTier(Contract12):
    from_ratio: Money   # inclusive lower bound of (optimum cost / reference value)
    pct: Money          # tolerance fraction of the optimum cost


DEFAULT_TIERS = [dict(from_ratio='0', pct='0.03'), dict(from_ratio='0.5', pct='0.02'), dict(from_ratio='5', pct='0.01')]


class Policy(Contract12):
    late_inbound_tolerance_days: StrictInt = Field(default=3, ge=0)   # C2 PROVISIONAL (reviewer: 2 to 3 days)
    late_inbound_credit: Money = Decimal('0.50')                      # C2 PROVISIONAL
    cost_tolerance_abs: Money = Decimal(0)
    cost_tolerance_reference_value: Money = Decimal('100.00')         # C3 PROVISIONAL: scale reference, USD
    cost_tolerance_tiers: list[ToleranceTier] = Field(                # C3 PROVISIONAL: 3% / 2% / 1%
        default_factory=lambda: [ToleranceTier(**t) for t in DEFAULT_TIERS])
    moq_excess_approval_threshold: Money = Decimal('500.00')          # C5 PROVISIONAL: reviewer gave no value

    @model_validator(mode='after')
    def shape(self):
        _ratio(self.late_inbound_credit, 'late_inbound_credit')
        if self.cost_tolerance_reference_value <= 0:
            raise ValueError('cost_tolerance_reference_value must be positive')
        tiers = self.cost_tolerance_tiers
        if not tiers or tiers[0].from_ratio != 0:
            raise ValueError('tolerance tiers must start at ratio 0')
        for a, b in zip(tiers, tiers[1:]):
            if b.from_ratio <= a.from_ratio:
                raise ValueError('tolerance tier bounds must strictly increase')
            if b.pct > a.pct:
                raise ValueError('tolerance must not loosen as order size grows')
        for t in tiers:
            _ratio(t.pct, 'tier pct')
        return self


class Approval(Contract12):
    """C5: a granted approval record visible in the world. Only MOQ excess approvals exist in 1.2."""
    approval_id: Identifier
    kind: Literal['moq_excess'] = 'moq_excess'
    item_id: Identifier


class Visibility(Contract12):
    classification: Literal['public_synthetic'] = 'public_synthetic'


class World(Contract12):
    world_id: Identifier
    seed: StrictInt
    currency: Literal['USD']
    calendar: Literal['gregorian'] = 'gregorian'
    as_of: date
    items: list[Item] = Field(min_length=1)
    stock: list[Stock]
    inbound: list[Inbound]
    suppliers: list[Supplier] = Field(min_length=1)
    quotes: list[Quote]
    constraints: Constraints
    policy: Policy = Field(default_factory=Policy)
    approvals: list[Approval] = Field(default_factory=list)
    visibility: Visibility

    @model_validator(mode='after')
    def references(self):
        items = [x.item_id for x in self.items]
        suppliers = [x.supplier_id for x in self.suppliers]
        if len(items) != len(set(items)) or len(suppliers) != len(set(suppliers)):
            raise ValueError('duplicate item or supplier ID')
        pairs = [(q.supplier_id, q.item_id) for q in self.quotes]
        if len(pairs) != len(set(pairs)):
            raise ValueError('duplicate supplier-item quote')
        for entry in [*self.stock, *self.inbound, *self.quotes, *self.approvals]:
            if entry.item_id not in items:
                raise ValueError('unknown item reference')
        if any(q.supplier_id not in suppliers for q in self.quotes):
            raise ValueError('unknown supplier reference')
        for rule in self.constraints.concentration:
            if any(i not in items for i in rule.item_ids or []):
                raise ValueError('concentration rule names an unknown item')
        ids = [a.approval_id for a in self.approvals]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate approval ID')
        return self


class Allocation(Contract12):
    supplier_id: Identifier
    item_id: Identifier
    quantity: Quantity


class AwardSubmission(Contract12):
    kind: Literal['award']
    allocations: list[Allocation]
    claimed_total_cost: Money
    evidence: list[str]
    # Flags: 'estimated:<supplier>:<item>' (C4) and 'moq_excess:<item>' (C5).
    flags: list[str] = Field(default_factory=list)
    # Missing quote fields the agent asked about first, e.g. 'quotes.A.component.variable_freight'.
    clarification_requests: list[str] = Field(default_factory=list)
    # C5: approval_id values of granted approval records that justify MOQ excess above the threshold.
    approval_refs: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique(self):
        pairs = [(a.supplier_id, a.item_id) for a in self.allocations]
        if len(pairs) != len(set(pairs)):
            raise ValueError('duplicate allocation')
        return self


class ExceptionSubmission(Contract12):
    kind: Literal['clarification', 'infeasible']
    evidence: list[str] = Field(min_length=1)
    # Missing quote term ('quotes.A.item.unit_price') or a needed approval ('approvals.moq_excess.<item>').
    field: str | None = None
    disposition: Literal['record_and_escalate'] | None = None


Submission = Annotated[AwardSubmission | ExceptionSubmission, Field(discriminator='kind')]


def parse_submission(value: Any) -> AwardSubmission | ExceptionSubmission:
    return TypeAdapter(Submission).validate_python(value)


class Task(Contract12):
    task_id: Identifier
    family: Literal['supplier_allocation'] = 'supplier_allocation'
    family_version: Literal['1.2'] = '1.2'
    world_id: Identifier
    request: str = Field(min_length=1)
    expected_outcome: Literal['award', 'clarification', 'infeasible']
    policy_version: Literal['1.2'] = '1.2'
    # C7: spend_share always applies by default; these name any EXTRA measures this task declares.
    concentration_measures: list[Literal['quantity_share', 'per_item_share']] = Field(default_factory=list)
    clarification_policy: dict[str, Literal['record_and_escalate']] = Field(default_factory=dict)


def check_task_world(task: Task, world: World) -> None:
    """C7: a world may use quantity or per-item share only when the task declares that measure."""
    for rule in world.constraints.concentration:
        if rule.measure != 'spend_share' and rule.measure not in task.concentration_measures:
            raise ValueError(f'task does not declare concentration measure {rule.measure}')
