"""Reference solver and heuristic for static rules 1.1. The checker shares none of this logic.

All policy numbers are PROVISIONAL (owner-practitioner review confirmed no value). Exact Decimal
arithmetic end to end: there is no per-supplier rounding in 1.1.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR
from math import isfinite
from time import monotonic
from typing import Literal

from .schemas_v11 import World

ZERO = Decimal(0)
SOLVER_VERSION = '1.1'


@dataclass(frozen=True)
class SolverResult11:
    status: Literal['optimal', 'feasible', 'infeasible', 'timeout', 'error', 'clarification_required']
    allocations: tuple[dict, ...] = ()
    total_cost: Decimal | None = None
    lower_bound: Decimal | None = None
    explored_states: int = 0
    message: str = ''
    clarification_field: str | None = None
    flags: tuple[str, ...] = ()
    clarification_requests: tuple[str, ...] = ()
    band_awards: tuple[tuple[Decimal, tuple[dict, ...]], ...] = ()  # feasible awards within the A3 band

    def submission(self):
        from .schemas_v11 import AwardSubmission, ExceptionSubmission
        if self.total_cost is not None:
            return AwardSubmission(kind='award', allocations=list(self.allocations), claimed_total_cost=self.total_cost,
                                   evidence=[self.message or 'Visible records and procurement policy'],
                                   flags=list(self.flags), clarification_requests=list(self.clarification_requests))
        if self.status == 'clarification_required':
            return ExceptionSubmission(kind='clarification', field=self.clarification_field,
                                       evidence=[self.message], disposition='record_and_escalate')
        if self.status == 'infeasible':
            return ExceptionSubmission(kind='infeasible', evidence=[self.message])
        raise ValueError('No supported final submission: solver outcome is unresolved.')


def _net(world, item):
    usable = sum(s.quantity for s in world.stock if s.item_id == item.item_id and s.status == 'usable')
    on_time = sum(s.quantity for s in world.inbound if s.item_id == item.item_id and s.arrival_date <= item.due_date)
    window = item.due_date + timedelta(days=world.policy.late_inbound_tolerance_days)
    late = sum(int((Decimal(s.quantity) * world.policy.late_inbound_credit).to_integral_value(rounding=ROUND_FLOOR))
              for s in world.inbound if s.item_id == item.item_id and item.due_date < s.arrival_date <= window)
    return max(0, item.demand + item.safety_stock - usable - on_time - late)


def _sizes(q):
    return [0] + [m for m in range(q.multiple, q.capacity + 1, q.multiple) if m >= q.moq]


def _floor(quotes, net):
    if net == 0:
        return 0
    best = None
    reach = {0}
    bound = net + max((max(_sizes(q)) for q in quotes), default=0)
    for q in quotes:
        reach = {r + s for r in reach for s in _sizes(q) if r + s <= bound}
    cands = [r for r in reach if r >= net]
    return min(cands) if cands else best


def _inputs(world):
    items = {i.item_id: i for i in world.items}
    needs = {k: _net(world, i) for k, i in items.items()}
    quotes = [q for q in world.quotes if q.qualified and q.valid_from <= world.as_of <= q.valid_to
              and q.arrival_date <= items[q.item_id].due_date]
    ceilings = {}
    for key, item in items.items():
        top = needs[key] + item.excess_allowance
        if item.moq_excess_allowed:
            f = _floor([q for q in quotes if q.item_id == key], needs[key])
            if f is not None:
                top = max(top, f)
        if item.max_excess is not None:
            top = min(top, needs[key] + item.max_excess)
        ceilings[key] = top
    missing = [f'quotes.{q.supplier_id}.{q.item_id}.{f}' for q in quotes
               for f in ('unit_price', 'variable_freight') if getattr(q, f) is None]
    return items, needs, quotes, ceilings, missing


def _unit_cost(q):
    """(unit cost, missing field names) using last known values for missing terms; None if unknowable."""
    parts, missing = [], []
    for f in ('unit_price', 'variable_freight'):
        v = getattr(q, f)
        if v is None:
            missing.append(f)
            v = getattr(q, 'last_known_' + f)
        if v is None:
            return None, missing
        parts.append(v)
    return parts[0] + parts[1], missing


def _charge(supplier, units, goods):
    if supplier.fixed_charge_basis == 'flat':
        return supplier.fixed_charge
    measure = Decimal(units) if supplier.fixed_charge_basis == 'order_units' else goods
    return [t.charge for t in supplier.fixed_charge_table if t.from_measure <= measure][-1]


def _evaluate(world, items, needs, ceilings, quotes, quantities):
    """Return (cost, flags, requests) for a feasible vector, else None."""
    totals = {k: 0 for k in items}
    goods, units, flags, requests = {}, {}, [], []
    for q, n in zip(quotes, quantities):
        totals[q.item_id] += n
        if not n:
            continue
        cost, missing = _unit_cost(q)
        if cost is None:
            return None
        if missing:
            limit = world.constraints.approval_limit
            if items[q.item_id].critical or limit is None or not n * cost < limit:
                return None
            flags.append(f'estimated:{q.supplier_id}:{q.item_id}')
            requests += [f'quotes.{q.supplier_id}.{q.item_id}.{f}' for f in missing]
        goods[q.supplier_id] = goods.get(q.supplier_id, ZERO) + n * cost
        units[q.supplier_id] = units.get(q.supplier_id, 0) + n
    for key, item in items.items():
        if not needs[key] <= totals[key] <= ceilings[key]:
            return None
        if totals[key] > needs[key] + item.excess_allowance:
            flags.append(f'moq_excess:{key}')
    sup = {s.supplier_id: s for s in world.suppliers}
    spend = {k: v + _charge(sup[k], units[k], v) for k, v in goods.items()}
    total = sum(spend.values(), ZERO)
    if total > world.constraints.budget:
        return None
    for rule in world.constraints.concentration:
        if rule.measure == 'spend_share':
            if total and any(v > rule.limit * total for v in spend.values()):
                return None
            continue
        scope = rule.item_ids if rule.item_ids is not None else list(items)
        per = {}
        for q, n in zip(quotes, quantities):
            if n and q.item_id in scope:
                per[(q.supplier_id, q.item_id)] = n
        if rule.measure == 'quantity_share':
            den = sum(per.values())
            by_sup = {}
            for (s, _), n in per.items():
                by_sup[s] = by_sup.get(s, 0) + n
            if den and any(v > rule.limit * den for v in by_sup.values()):
                return None
        else:
            for key in scope:
                den = sum(n for (_, i), n in per.items() if i == key)
                if any(n > rule.limit * den for (_, i), n in per.items() if i == key):
                    return None
    return total, tuple(flags), tuple(dict.fromkeys(requests))


def _allocations(quotes, quantities):
    return tuple(dict(supplier_id=q.supplier_id, item_id=q.item_id, quantity=n) for q, n in zip(quotes, quantities) if n)


def solve_reference(world: World, *, time_limit_seconds: float = 5.0, max_states: int = 1_000_000,
                    band_limit: int = 200) -> SolverResult11:
    started = monotonic()
    if not isfinite(time_limit_seconds) or time_limit_seconds < 0 or not isinstance(max_states, int) or max_states < 0:
        return SolverResult11('error', message='Search limits must be finite and nonnegative; max_states must be integral.')
    items, needs, quotes, ceilings, missing = _inputs(world)
    found = []   # (cost, allocs, flags, requests)
    visited, interrupted = 0, False
    quantities = [0] * len(quotes)
    totals = {k: 0 for k in items}

    def search(index):
        nonlocal visited, interrupted
        if visited >= max_states or monotonic() - started >= time_limit_seconds:
            interrupted = True
            return
        visited += 1
        if index == len(quotes):
            r = _evaluate(world, items, needs, ceilings, quotes, quantities)
            if r is not None:
                found.append((r[0], _allocations(quotes, quantities), r[1], r[2]))
            return
        q = quotes[index]
        room = ceilings[q.item_id] - totals[q.item_id]
        for n in _sizes(q):
            if n > room:
                break
            quantities[index] = n
            totals[q.item_id] += n
            search(index + 1)
            totals[q.item_id] -= n
            if interrupted:
                break
        quantities[index] = 0

    try:
        search(0)
    except RecursionError:
        return SolverResult11('error', explored_states=visited, message='Quote count exceeded recursive search capacity; outcome unresolved.')
    if interrupted:
        return SolverResult11('timeout', explored_states=visited, lower_bound=ZERO,
                              message='Search limit reached; infeasibility and optimality unproven.')
    if not found:
        if missing:
            return SolverResult11('clarification_required', explored_states=visited, clarification_field=missing[0],
                                  message=f'Missing commercial term: {missing[0]}; request it and escalate. No zero substitution; estimate not permitted for this order.')
        short = [k for k in items if sum(max(_sizes(q)) for q in quotes if q.item_id == k) < needs[k]]
        return SolverResult11('infeasible', explored_states=visited, lower_bound=ZERO,
                              message='Exhaustive integral enumeration completed.' + (
                                  ' Eligible capacity shortfall: ' + ', '.join(
                                      f'{k}: eligible capacity is less than net requirement {needs[k]}' for k in short) if short else ''))
    best = min(found, key=lambda r: r[0])
    tol = max(world.policy.cost_tolerance_abs, world.policy.cost_tolerance_pct * best[0])
    band = tuple((c, a) for c, a, _, _ in sorted(found, key=lambda r: r[0]) if c - best[0] <= tol)[:band_limit]
    return SolverResult11('optimal', best[1], best[0], best[0], visited,
                          'Exhaustive integral enumeration completed (rules 1.1, exact arithmetic).',
                          flags=best[2], clarification_requests=best[3], band_awards=band)


def solve_heuristic(world: World) -> SolverResult11:
    """Greedy by landed unit cost (estimates allowed where permitted); fixed tiers and policy may defeat it."""
    items, needs, quotes, ceilings, missing = _inputs(world)
    priced = [i for i in range(len(quotes)) if _unit_cost(quotes[i])[0] is not None]
    remaining = dict(needs)
    quantities = [0] * len(quotes)
    for index in sorted(priced, key=lambda i: (_unit_cost(quotes[i])[0], quotes[i].supplier_id)):
        q = quotes[index]
        if remaining[q.item_id] <= 0:
            continue
        sizes = [s for s in _sizes(q) if s]
        fits = [s for s in sizes if s >= remaining[q.item_id] and s <= remaining[q.item_id] + (ceilings[q.item_id] - needs[q.item_id])]
        under = [s for s in sizes if s <= remaining[q.item_id]]
        pick = min(fits) if fits else (max(under) if under else None)
        if pick is None:
            continue
        quantities[index] = pick
        remaining[q.item_id] -= pick
    result = _evaluate(world, items, needs, ceilings, quotes, quantities)
    if result is None:
        return SolverResult11('error', message='Greedy construction failed policy validation; feasibility remains unknown.')
    return SolverResult11('feasible', _allocations(quotes, quantities), result[0], ZERO,
                          message='Greedy landed-cost allocation; no optimality guarantee.',
                          flags=result[1], clarification_requests=result[2])
