"""Versioned public contracts. Validation is structural, not a feasibility verdict."""
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, StrictInt, StrictBool, TypeAdapter, model_validator


def decimal_value(value: Any) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise ValueError('decimal values must be strings or Decimal, never floats')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid decimal') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('decimal must be finite and nonnegative')
    return result

Money = Annotated[Decimal, BeforeValidator(decimal_value)]
Quantity = Annotated[StrictInt, Field(ge=0)]
Identifier = Annotated[str, Field(min_length=1, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')]

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    schema_version: Literal['1.0'] = '1.0'

class Item(Contract):
    item_id: Identifier
    unit: Literal['each'] = 'each'
    demand: Quantity
    due_date: date
    excess_allowance: Quantity = 0

class Stock(Contract):
    item_id: Identifier
    quantity: Quantity
    status: Literal['usable', 'held', 'reserved']

class Inbound(Contract):
    item_id: Identifier
    quantity: Quantity
    arrival_date: date
    status: Literal['committed'] = 'committed'

class Supplier(Contract):
    supplier_id: Identifier
    fixed_charge: Money

class Quote(Contract):
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

    @model_validator(mode='after')
    def valid_window(self):
        if self.valid_to < self.valid_from:
            raise ValueError('quote validity window is reversed')
        return self

class Constraints(Contract):
    budget: Money
    concentration_limit: Money | None = None

    @model_validator(mode='after')
    def ratio(self):
        if self.concentration_limit is not None and self.concentration_limit > 1:
            raise ValueError('concentration_limit must be in [0,1]')
        return self

class Visibility(Contract):
    classification: Literal['public_synthetic'] = 'public_synthetic'

class World(Contract):
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
        return self

class Allocation(Contract):
    supplier_id: Identifier
    item_id: Identifier
    quantity: Quantity

class AwardSubmission(Contract):
    kind: Literal['award']
    allocations: list[Allocation]
    claimed_total_cost: Money
    evidence: list[str]

    @model_validator(mode='after')
    def unique(self):
        pairs = [(a.supplier_id, a.item_id) for a in self.allocations]
        if len(pairs) != len(set(pairs)):
            raise ValueError('duplicate allocation')
        return self

class ExceptionSubmission(Contract):
    kind: Literal['clarification', 'infeasible']
    evidence: list[str] = Field(min_length=1)
    field: str | None = None

Submission = Annotated[AwardSubmission | ExceptionSubmission, Field(discriminator='kind')]
def parse_submission(value: Any) -> AwardSubmission | ExceptionSubmission:
    return TypeAdapter(Submission).validate_python(value)

class Task(Contract):
    task_id: Identifier
    family: Literal['supplier_allocation'] = 'supplier_allocation'
    family_version: Literal['1.0'] = '1.0'
    world_id: Identifier
    lineage: Identifier
    split: Literal['train', 'development', 'evaluation']
    request: str = Field(min_length=1)
    visible_artifacts: list[str]
    permitted_tools: list[str]
    expected_outcome: Literal['award', 'clarification', 'infeasible']
    policy_version: Literal['1.0'] = '1.0'
    runtime_version: Literal['1.0'] = '1.0'
    clarification_policy: dict[str, Literal['record_and_escalate']] = Field(default_factory=dict)
    restrictions: list[str] = Field(default_factory=lambda: ['one_period', 'one_facility', 'integral_units', 'USD', 'no_taxes', 'no_fx', 'no_price_tiers'])

class Action(Contract):
    tool_name: Identifier
    arguments: dict[str, Any]
    request_id: Identifier
    state_version: Quantity

class TypedError(Contract):
    code: Identifier
    message: str

class ActionResult(Contract):
    request_id: Identifier
    observation: dict[str, Any] | None = None
    error: TypedError | None = None
    simulated_time: date | None = None
    state_version: Quantity

    @model_validator(mode='after')
    def exactly_one(self):
        if (self.observation is None) == (self.error is None):
            raise ValueError('exactly one of observation or error is required')
        return self

class Trajectory(Contract):
    run_id: Identifier
    task_id: Identifier
    model_id: Identifier
    configuration: dict[str, Any]
    observations: list[dict[str, Any]]
    actions: list[Action]
    results: list[ActionResult]
    final_submission: Submission
    termination_reason: Literal['submitted', 'tool_limit', 'timeout', 'error']
    artifact_hashes: dict[str, Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]]
    usage: dict[str, Quantity]
    cost: Money

    @model_validator(mode='after')
    def ordered_requests(self):
        ids = [a.request_id for a in self.actions]
        if len(ids) != len(set(ids)) or ids != [r.request_id for r in self.results]:
            raise ValueError('actions/results must have unique matching ordered request IDs')
        return self

class ConstraintResult(Contract):
    name: Identifier
    passed: bool
    detail: str

class Verification(Contract):
    checker_version: Literal['1.0'] = '1.0'
    task_status: Literal['accepted', 'rejected', 'error']
    constraints: list[ConstraintResult]
    independent_cost: Money | None
    reference_status: Literal['optimal', 'feasible', 'infeasible', 'timeout', 'error', 'unavailable']
    reference_bound: Money | None = None
    objective_gap: Money | None = None
    critical_failures: list[str]
    evidence: list[str]

class ManifestEntry(Contract):
    task_id: Identifier
    lineage: Identifier
    split: Literal['train', 'development', 'evaluation']
    trajectory_hash: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]

class ExportManifest(Contract):
    dataset_version: Identifier
    accepted: list[ManifestEntry]
    runtime_version: Literal['1.0'] = '1.0'
    source_use_status: Literal['synthetic_public']
    filtering_reasons: dict[str, Quantity]
    accepted_count: Quantity
    rejected_count: Quantity

    @model_validator(mode='after')
    def split_integrity(self):
        if self.accepted_count != len(self.accepted):
            raise ValueError('accepted_count mismatch')
        ids = [x.task_id for x in self.accepted]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate accepted task')
        splits: dict[str, str] = {}
        for entry in self.accepted:
            if splits.setdefault(entry.lineage, entry.split) != entry.split:
                raise ValueError('lineage crosses splits')
        return self
