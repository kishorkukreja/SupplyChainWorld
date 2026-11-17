"""Reference solver and heuristic for static rules 1.2. The checker shares none of this logic.

All policy numbers are PROVISIONAL (owner-practitioner re-review confirmed no value). Exact Decimal arithmetic
end to end. Reuses the v1.1 order-size, floor, unit-cost and fixed-charge helpers by import; rules that changed in
1.2 (service-level safety stock, estimate boundary, MOQ approval, ask-first, tiered tolerance) are re-implemented here.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from math import isfinite
from time import monotonic
from typing import Literal

from .schemas_v12 import World, Z_TABLE
from .solvers_v11 import ZERO, _charge, _floor, _sizes, _unit_cost

SOLVER_VERSION = '1.2'


@dataclass(frozen=True)
class SolverResult12:
    status: Literal['optimal', 'feasible', 'infeasible', 'timeout', 'error', 'clarification_required']
    allocations: tuple[dict, ...] = ()
    total_cost: Decimal | None = None
    lower_bound: Decimal | None = None
    explored_states: int = 0
    message: str = ''
    clarification_field: str | None = None
    flags: tuple[str, ...] = ()
    clarification_requests: tuple[str, ...] = ()
    approval_refs: tuple[str, ...] = ()
    band_awards: tuple[tuple[Decimal, tuple[dict, ...]], ...] = ()

    def submission(self):
        from .schemas_v12 import AwardSubmission, ExceptionSubmission
        if self.total_cost is not None:
            return AwardSubmission(kind='award', allocations=list(self.allocations), claimed_total_cost=self.total_cost,
                                   evidence=[self.message or 'Visible records and procurement policy'],
                                   flags=list(self.flags), clarification_requests=list(self.clarification_requests),
                                   approval_refs=list(self.approval_refs))
        if self.status == 'clarification_required':
            return ExceptionSubmission(kind='clarification', field=self.clarification_field,
                                       evidence=[self.message], disposition='record_and_escalate')
        if self.status == 'infeasible':
            return ExceptionSubmission(kind='infeasible', evidence=[self.message])
        raise ValueError('No supported final submission: solver outcome is unresolved.')


def safety_stock(item) -> int:
    """C1: ceil(z x std x sqrt(lead)) via a high-precision Decimal square root (exact for perfect squares)."""
    if item.safety_stock_override is not None:
        return item.safety_stock_override
    if item.service_level is None:
        return 0
    with localcontext() as ctx:
        ctx.prec = 120
        root = ((Z_TABLE[item.service_level] * item.demand_std) ** 2 * item.lead_time_periods).sqrt()
        return int(root.to_integral_value(rounding=ROUND_CEILING))


def tolerance_pct(world: World, optimum: Decimal) -> Decimal:
    pct = ZERO
    for tier in world.policy.cost_tolerance_tiers:
        if optimum >= tier.from_ratio * world.policy.cost_tolerance_reference_value:
            pct = tier.pct
    return pct


def _net(world, item):
    usable = sum(s.quantity for s in world.stock if s.item_id == item.item_id and s.status == 'usable')
    on_time = sum(s.quantity for s in world.inbound if s.item_id == item.item_id and s.arrival_date <= item.due_date)
    window = item.due_date + timedelta(days=world.policy.late_inbound_tolerance_days)
    late = sum(int((Decimal(s.quantity) * world.policy.late_inbound_credit).to_integral_value(rounding=ROUND_FLOOR))
              for s in world.inbound if s.item_id == item.item_id and item.due_date < s.arrival_date <= window)
    return max(0, item.demand + safety_stock(item) - usable - on_time - late)


def _inputs(world):
    items = {i.item_id: i for i in world.items}
    needs = {k: _net(world, i) for k, i in items.items()}
    quotes = [q for q in world.quotes if q.qualified and q.valid_from <= world.as_of <= q.valid_to
              and q.arrival_date <= items[q.item_id].due_date]
    limit = world.constraints.approval_limit
    blocking = []   # C6: missing terms the estimate path cannot cover; ask first, never award around them
    for q in quotes:
        if needs[q.item_id] == 0:
            continue
        names = [f for f in ('unit_price', 'variable_freight') if getattr(q, f) is None]
        if not names:
            continue
        cost, _ = _unit_cost(q)
        ref_qty = min(q.capacity, max(needs[q.item_id], q.moq))
        covered = cost is not None and not items[q.item_id].critical and limit is not None and ref_qty * cost <= limit
        if not covered:
            blocking += [f'quotes.{q.supplier_id}.{q.item_id}.{f}' for f in names]
    ceilings, approval_fields = {}, []
    approved = {a.item_id for a in world.approvals if a.kind == 'moq_excess'}
    for key, item in items.items():
        top = needs[key] + item.excess_allowance
        if item.moq_excess_allowed and needs[key]:
            f = _floor([q for q in quotes if q.item_id == key], needs[key])
            if f is not None:
                top = max(top, f)
                if f > needs[key] + item.excess_allowance and key not in approved:
                    approval_fields.append(f'approvals.moq_excess.{key}')
        if item.max_excess is not None:
            top = min(top, needs[key] + item.max_excess)
        ceilings[key] = top
    return items, needs, quotes, ceilings, blocking, approval_fields


def _evaluate(world, items, needs, ceilings, quotes, quantities):
    """Return (cost, flags, requests, approval_refs) for a feasible vector, else None."""
    totals = {k: 0 for k in items}
    goods, units, flags, requests, item_goods = {}, {}, [], [], {k: ZERO for k in items}
    for q, n in zip(quotes, quantities):
        totals[q.item_id] += n
        if not n:
            continue
        cost, missing = _unit_cost(q)
        if cost is None:
            return None
        if missing:
            limit = world.constraints.approval_limit
            if items[q.item_id].critical or limit is None or not n * cost <= limit:   # C4: at or below the limit
                return None
            flags.append(f'estimated:{q.supplier_id}:{q.item_id}')
            requests += [f'quotes.{q.supplier_id}.{q.item_id}.{f}' for f in missing]
        goods[q.supplier_id] = goods.get(q.supplier_id, ZERO) + n * cost
        units[q.supplier_id] = units.get(q.supplier_id, 0) + n
        item_goods[q.item_id] += n * cost
    refs = []
    for key, item in items.items():
        if not needs[key] <= totals[key] <= ceilings[key]:
            return None
        if totals[key] > needs[key] + item.excess_allowance:
            flags.append(f'moq_excess:{key}')
            excess = totals[key] - needs[key] - item.excess_allowance
            if excess * item_goods[key] > world.policy.moq_excess_approval_threshold * totals[key]:   # C5
                ids = sorted(a.approval_id for a in world.approvals if a.kind == 'moq_excess' and a.item_id == key)
                if not ids:
                    return None
                refs.append(ids[0])
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
    return total, tuple(flags), tuple(dict.fromkeys(requests)), tuple(refs)


def _allocations(quotes, quantities):
    return tuple(dict(supplier_id=q.supplier_id, item_id=q.item_id, quantity=n) for q, n in zip(quotes, quantities) if n)


def solve_reference(world: World, *, time_limit_seconds: float = 5.0, max_states: int = 1_000_000,
                    band_limit: int = 200) -> SolverResult12:
    started = monotonic()
    if not isfinite(time_limit_seconds) or time_limit_seconds < 0 or not isinstance(max_states, int) or max_states < 0:
        return SolverResult12('error', message='Search limits must be finite and nonnegative; max_states must be integral.')
    items, needs, quotes, ceilings, blocking, approval_fields = _inputs(world)
    if blocking:    # C6: ask clarification first; the estimate path does not cover this gap
        return SolverResult12('clarification_required', clarification_field=blocking[0],
                              message=f'Missing commercial term: {blocking[0]}; request it and escalate. No zero substitution and no award around the gap; the estimate path does not apply.')
    found = []
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
                found.append((r[0], _allocations(quotes, quantities), r[1], r[2], r[3]))
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
        return SolverResult12('error', explored_states=visited, message='Quote count exceeded recursive search capacity; outcome unresolved.')
    if interrupted:
        return SolverResult12('timeout', explored_states=visited, lower_bound=ZERO,
                              message='Search limit reached; infeasibility and optimality unproven.')
    if not found:
        if approval_fields:
            return SolverResult12('clarification_required', explored_states=visited, clarification_field=approval_fields[0],
                                  message=f'MOQ forces excess and no approval is on file: request {approval_fields[0]} and escalate. No award is acceptable without it.')
        short = [k for k in items if sum(max(_sizes(q)) for q in quotes if q.item_id == k) < needs[k]]
        return SolverResult12('infeasible', explored_states=visited, lower_bound=ZERO,
                              message='Exhaustive integral enumeration completed.' + (
                                  ' Eligible capacity shortfall: ' + ', '.join(
                                      f'{k}: eligible capacity is less than net requirement {needs[k]}' for k in short) if short else ''))
    best = min(found, key=lambda r: r[0])
    tol = max(world.policy.cost_tolerance_abs, tolerance_pct(world, best[0]) * best[0])
    band = tuple((c, a) for c, a, *_ in sorted(found, key=lambda r: r[0]) if c - best[0] <= tol)[:band_limit]
    return SolverResult12('optimal', best[1], best[0], best[0], visited,
                          'Exhaustive integral enumeration completed (rules 1.2, exact arithmetic).',
                          flags=best[2], clarification_requests=best[3], approval_refs=best[4], band_awards=band)


def solve_heuristic(world: World) -> SolverResult12:
    """Greedy by landed unit cost; refuses to award around a gap that needs clarification. No optimality guarantee."""
    items, needs, quotes, ceilings, blocking, approval_fields = _inputs(world)
    if blocking:
        return SolverResult12('clarification_required', clarification_field=blocking[0],
                              message=f'Missing commercial term: {blocking[0]}; request it and escalate.')
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
        if approval_fields:
            return SolverResult12('clarification_required', clarification_field=approval_fields[0],
                                  message=f'MOQ excess needs approval: request {approval_fields[0]} and escalate.')
        return SolverResult12('error', message='Greedy construction failed policy validation; feasibility remains unknown.')
    return SolverResult12('feasible', _allocations(quotes, quantities), result[0], ZERO,
                          message='Greedy landed-cost allocation; no optimality guarantee.',
                          flags=result[1], clarification_requests=result[2], approval_refs=result[3])
