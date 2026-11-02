"""Small-instance baselines. The checker deliberately does not share this logic."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from time import monotonic
from math import isfinite
from typing import Literal

from .schemas import World

ZERO = Decimal('0')
CENT = Decimal('.01')


@dataclass(frozen=True)
class SolverResult:
    status: Literal['optimal', 'feasible', 'infeasible', 'timeout', 'error', 'clarification_required']
    allocations: tuple[dict, ...] = ()
    total_cost: Decimal | None = None
    lower_bound: Decimal | None = None
    explored_states: int = 0
    message: str = ''
    clarification_field: str | None = None

    def submission(self):
        from .schemas import AwardSubmission, ExceptionSubmission
        if self.total_cost is not None:
            return AwardSubmission(kind='award', allocations=list(self.allocations), claimed_total_cost=self.total_cost,
                                   evidence=[self.message or 'Visible records and procurement policy'])
        if self.status == 'clarification_required':
            return ExceptionSubmission(kind='clarification', field=self.clarification_field,
                                       evidence=[self.message])
        if self.status == 'infeasible':
            return ExceptionSubmission(kind='infeasible', evidence=[self.message])
        raise ValueError('No supported final submission: solver outcome is unresolved.')


def _inputs(world):
    items = {i.item_id: i for i in world.items}
    needs = {}
    for key, item in items.items():
        available = sum(s.quantity for s in world.stock if s.item_id == key and s.status == 'usable')
        available += sum(s.quantity for s in world.inbound if s.item_id == key and
                         s.status == 'committed' and s.arrival_date <= item.due_date)
        needs[key] = max(0, item.demand - available)
    quotes = [q for q in world.quotes if q.qualified and q.valid_from <= world.as_of <= q.valid_to
              and q.arrival_date <= items[q.item_id].due_date]
    missing = next((f'quotes.{q.supplier_id}.{q.item_id}.{field}' for q in quotes
                    for field in ('unit_price', 'variable_freight') if getattr(q, field) is None), None)
    if missing is None:
        missing = next((f'suppliers.{s.supplier_id}.fixed_charge' for s in world.suppliers
                        if s.fixed_charge is None and any(q.supplier_id == s.supplier_id for q in quotes)), None)
    return items, needs, quotes, missing


def _cost_if_feasible(world, items, needs, quotes, quantities):
    totals = {key: 0 for key in items}
    spend = {}
    for q, quantity in zip(quotes, quantities):
        totals[q.item_id] += quantity
        if quantity:
            spend[q.supplier_id] = spend.get(q.supplier_id, ZERO) + quantity * (q.unit_price + q.variable_freight)
    if any(not needs[key] <= totals[key] <= needs[key] + item.excess_allowance for key, item in items.items()):
        return None
    fees = {s.supplier_id: s.fixed_charge for s in world.suppliers}
    spend = {key: (value + fees[key]).quantize(CENT, rounding=ROUND_HALF_UP) for key, value in spend.items()}
    total = sum(spend.values(), ZERO)
    if total > world.constraints.budget:
        return None
    limit = world.constraints.concentration_limit
    if total and limit is not None and any(value > limit * total for value in spend.values()):
        return None
    return total


def _allocations(quotes, quantities):
    return tuple(dict(supplier_id=q.supplier_id, item_id=q.item_id, quantity=n)
                 for q, n in zip(quotes, quantities) if n)


def solve_reference(world: World, *, time_limit_seconds: float = 5.0, max_states: int = 1_000_000) -> SolverResult:
    """Enumerate bounded integral domains; timeout never establishes infeasibility.

    A state is a visited search-tree node, including root and complete vectors.
    A zero lower bound is safe because schemas require nonnegative costs.
    """
    started = monotonic()
    if not isfinite(time_limit_seconds) or time_limit_seconds < 0 or not isinstance(max_states, int) or max_states < 0:
        return SolverResult('error', message='Search limits must be finite and nonnegative; max_states must be integral.')
    items, needs, quotes, missing = _inputs(world)
    if missing:
        return SolverResult('clarification_required', message=f'Missing commercial term: {missing}', clarification_field=missing)
    incumbent = None
    best = ()
    visited = 0
    interrupted = False
    quantities = [0] * len(quotes)
    totals = {key: 0 for key in items}

    def search(index):
        nonlocal incumbent, best, visited, interrupted
        if visited >= max_states or monotonic() - started >= time_limit_seconds:
            interrupted = True
            return
        visited += 1
        if index == len(quotes):
            cost = _cost_if_feasible(world, items, needs, quotes, quantities)
            if cost is not None and (incumbent is None or cost < incumbent):
                incumbent, best = cost, _allocations(quotes, quantities)
            return
        q = quotes[index]
        ceiling = min(q.capacity, needs[q.item_id] + items[q.item_id].excess_allowance - totals[q.item_id])
        first = max(1, (q.moq + q.multiple - 1) // q.multiple) * q.multiple
        def choices():
            yield 0
            yield from range(first, ceiling + 1, q.multiple)
        for quantity in choices():
            quantities[index] = quantity
            totals[q.item_id] += quantity
            search(index + 1)
            totals[q.item_id] -= quantity
            if interrupted:
                break
    try:
        search(0)
    except RecursionError:
        return SolverResult('error', best, incumbent, ZERO, visited,
                            'Quote count exceeded recursive search capacity; outcome unresolved.')
    status = 'timeout' if interrupted else ('optimal' if incumbent is not None else 'infeasible')
    return SolverResult(status, best, incumbent, incumbent if status == 'optimal' else ZERO, visited,
                        'Search limit reached; infeasibility and optimality unproven.' if interrupted else
                        ('Exhaustive integral enumeration completed. Eligible capacity shortfall: ' +
                         ', '.join(key for key in items if sum(q.capacity for q in quotes if q.item_id == key) < needs[key]))
                        if status == 'infeasible' and any(sum(q.capacity for q in quotes if q.item_id == key) < needs[key] for key in items)
                        else 'Exhaustive integral enumeration completed.')


def solve_heuristic(world: World) -> SolverResult:
    """Greedy by variable landed unit cost; fixed fees and policy may defeat it."""
    items, needs, quotes, missing = _inputs(world)
    if missing:
        return SolverResult('clarification_required', message=f'Missing commercial term: {missing}', clarification_field=missing)
    remaining = dict(needs)
    quantities = [0] * len(quotes)
    for index in sorted(range(len(quotes)), key=lambda i: (quotes[i].unit_price + quotes[i].variable_freight, quotes[i].supplier_id)):
        q = quotes[index]
        if remaining[q.item_id] <= 0:
            continue
        quantity = max(q.moq, remaining[q.item_id])
        quantity = ((quantity + q.multiple - 1) // q.multiple) * q.multiple
        quantity = min(quantity, (q.capacity // q.multiple) * q.multiple)
        if quantity < q.moq or quantity > remaining[q.item_id] + items[q.item_id].excess_allowance:
            continue
        quantities[index] = quantity
        remaining[q.item_id] -= quantity
    cost = _cost_if_feasible(world, items, needs, quotes, quantities)
    if cost is None:
        return SolverResult('error', message='Greedy construction failed policy validation; feasibility remains unknown.')
    return SolverResult('feasible', _allocations(quotes, quantities), cost, ZERO,
                        message='Greedy variable-cost allocation; no optimality guarantee.')
