"""Static supplier-allocation contracts, schema/rules version 1.1 (REPAIR-17a, issue #35).

Lives beside the frozen 1.0 contracts in ``schemas.py``; nothing here changes 1.0.
Every numeric policy value that a fixture sets is PROVISIONAL: the owner-practitioner
review did not confirm any number. See docs/acceptance/static-v1.1-provisional-values.md.
"""
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, TypeAdapter, model_validator

from .schemas import Identifier, Money, Quantity

VERSION = '1.1'
Ratio = Annotated[Money, Field()]


def _ratio(value: Decimal | None, name: str):
    if value is not None and value > 1:
        raise ValueError(f'{name} must be in [0,1]')


class Contract11(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    schema_version: Literal['1.1'] = '1.1'


class Item(Contract11):
    item_id: Identifier
    unit: Literal['each'] = 'each'
    demand: Quantity
    due_date: date
    excess_allowance: Quantity = 0          # explicit permitted excess over net requirement
    safety_stock: Quantity = 0              # A1: target held on top of demand
    critical: StrictBool = False            # A4: critical parts always escalate on missing terms
    moq_excess_allowed: StrictBool = False  # A6: MOQ may justify excess beyond allowance, with a flag
    max_excess: Quantity | None = None      # A6: shelf-life / obsolescence cap on ALL excess


class Stock(Contract11):
    item_id: Identifier
    quantity: Quantity
    status: Literal['usable', 'held', 'reserved']


class Inbound(Contract11):
    item_id: Identifier
    quantity: Quantity
    arrival_date: date
    status: Literal['committed'] = 'committed'


class FixedChargeTier(Contract11):
    from_measure: Money   # inclusive lower bound of the basis measure (units or goods value)
    charge: Money


class Supplier(Contract11):
    supplier_id: Identifier
    fixed_charge: Money | None = None                              # flat charge (basis 'flat')
    fixed_charge_basis: Literal['flat', 'order_units', 'order_value'] = 'flat'
    fixed_charge_table: list[FixedChargeTier] = Field(default_factory=list)  # A5: table-driven
    reliability_score: Money | None = None                         # A3: report-only metric in [0,1]

    @model_validator(mode='after')
    def charge_shape(self):
        _ratio(self.reliability_score, 'reliability_score')
        if self.fixed_charge_basis == 'flat':
            if self.fixed_charge is None or self.fixed_charge_table:
                raise ValueError('flat basis needs fixed_charge and no table')
        else:
            if self.fixed_charge is not None or not self.fixed_charge_table:
                raise ValueError('tiered basis needs a table and no flat fixed_charge')
            starts = [t.from_measure for t in self.fixed_charge_table]
            if starts[0] != 0 or any(b <= a for a, b in zip(starts, starts[1:])):
                raise ValueError('fixed charge table must start at 0 and strictly increase')
        return self


class Quote(Contract11):
    supplier_id: Identifier
    item_id: Identifier
    unit_price: Money | None
    variable_freight: Money | None
    capacity: Quantity
    moq: Quantity
    multiple: Annotated[StrictInt, Field(gt=0)]
    qualified: StrictBool
    valid_from: date
    valid_to: date
    arrival_date: date
    last_known_unit_price: Money | None = None        # A4
    last_known_variable_freight: Money | None = None  # A4
    lead_time_risk: Money | None = None               # A3: report-only metric in [0,1]

    @model_validator(mode='after')
    def valid_window(self):
        if self.valid_to < self.valid_from:
            raise ValueError('quote validity window is reversed')
        _ratio(self.lead_time_risk, 'lead_time_risk')
        return self


class ConcentrationRule(Contract11):
    """A2: each task declares which measure(s) apply. All comparisons are exact."""
    measure: Literal['spend_share', 'quantity_share', 'per_item_share']
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


class Constraints(Contract11):
    budget: Money
    concentration: list[ConcentrationRule] = Field(default_factory=list)
    approval_limit: Money | None = None  # A4


class Policy(Contract11):
    late_inbound_tolerance_days: StrictInt = Field(default=0, ge=0)  # A1
    late_inbound_credit: Money = Decimal(0)                          # A1: fraction of a late line counted
    cost_tolerance_abs: Money = Decimal(0)                           # A3
    cost_tolerance_pct: Money = Decimal(0)                           # A3

    @model_validator(mode='after')
    def ratios(self):
        _ratio(self.late_inbound_credit, 'late_inbound_credit')
        _ratio(self.cost_tolerance_pct, 'cost_tolerance_pct')
        return self


class Visibility(Contract11):
    classification: Literal['public_synthetic'] = 'public_synthetic'


class World(Contract11):
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
        for entry in [*self.stock, *self.inbound, *self.quotes]:
            if entry.item_id not in items:
                raise ValueError('unknown item reference')
        if any(q.supplier_id not in suppliers for q in self.quotes):
            raise ValueError('unknown supplier reference')
        for rule in self.constraints.concentration:
            if any(i not in items for i in rule.item_ids or []):
                raise ValueError('concentration rule names an unknown item')
        return self


class Allocation(Contract11):
    supplier_id: Identifier
    item_id: Identifier
    quantity: Quantity


class AwardSubmission(Contract11):
    kind: Literal['award']
    allocations: list[Allocation]
    claimed_total_cost: Money
    evidence: list[str]
    # Flags: 'estimated:<supplier>:<item>' (A4) and 'moq_excess:<item>' (A6).
    flags: list[str] = Field(default_factory=list)
    # Missing quote fields the agent asked about first (A4), e.g. 'quotes.A.component.variable_freight'.
    clarification_requests: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique(self):
        pairs = [(a.supplier_id, a.item_id) for a in self.allocations]
        if len(pairs) != len(set(pairs)):
            raise ValueError('duplicate allocation')
        return self


class ExceptionSubmission(Contract11):
    kind: Literal['clarification', 'infeasible']
    evidence: list[str] = Field(min_length=1)
    field: str | None = None
    disposition: Literal['record_and_escalate'] | None = None


Submission = Annotated[AwardSubmission | ExceptionSubmission, Field(discriminator='kind')]


def parse_submission(value: Any) -> AwardSubmission | ExceptionSubmission:
    return TypeAdapter(Submission).validate_python(value)


class Task(Contract11):
    task_id: Identifier
    family: Literal['supplier_allocation'] = 'supplier_allocation'
    family_version: Literal['1.1'] = '1.1'
    world_id: Identifier
    request: str = Field(min_length=1)
    expected_outcome: Literal['award', 'clarification', 'infeasible']
    policy_version: Literal['1.1'] = '1.1'
    concentration_measures: list[Literal['spend_share', 'quantity_share', 'per_item_share']] = Field(default_factory=list)
    clarification_policy: dict[str, Literal['record_and_escalate']] = Field(default_factory=dict)
