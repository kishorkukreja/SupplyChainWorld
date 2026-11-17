"""Independent business checker for static rules 1.2; imports no solver code.

Rules (all numeric parameters in fixtures are PROVISIONAL, see docs/acceptance/static-v1.2-provisional-values.md):
  C1 safety stock = ceil(z(service_level) x demand_std x sqrt(lead_time_periods)) from a fixed z-table, evaluated
     exactly as the smallest integer s with s*s >= (z x std)^2 x lead_time (Fraction arithmetic, no sqrt, no float);
     an explicit override replaces the computed value. net = max(0, demand + SS - usable - on-time inbound - late credit).
  C2 late inbound arriving 1..tolerance days after the deadline earns floor(quantity x credit) units (tolerance 3 days).
  C3 equivalent-to-optimal if gap <= absolute band or gap <= tier pct x optimum; the tier is chosen by
     optimum / reference value (monotone: larger orders never get a looser tolerance). Exact gap always reported.
  C4 missing price/freight: an estimate on last known terms is allowed when the line value is AT OR BELOW the approval
     limit and the item is not critical; flagged and requested. Never zero.
  C5 MOQ excess needs an approval: always flagged; above the value threshold it also needs a granted approval reference.
  C6 ask clarification FIRST: if an eligible quote for a needed item has a missing term and the estimate path does not
     apply to that quote, no award is acceptable; the answer is a clarification, never an award around the gap.
  C7 concentration: spend_share by default; quantity and per-item share only when the task declares them.
  C8 no rounding anywhere; exact Decimal totals.
"""
from dataclasses import dataclass, field
from datetime import date as _date, timedelta
from decimal import Decimal, ROUND_FLOOR
from fractions import Fraction
from typing import Any

from .verification_v11 import _order_sizes, _reachable_floor, _tier_charge

CHECKER_VERSION = "1.2"
METRIC_PLACES = Decimal("0.0001")


@dataclass
class VerificationResult12:
    accepted: bool
    outcome: str
    independent_cost: Decimal | None = None
    critical_failures: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    objective_gap: Decimal | None = None
    objective_gap_pct: Decimal | None = None
    optimality: str | None = None
    estimated_lines: list[str] = field(default_factory=list)
    net_requirements: dict[str, int] = field(default_factory=dict)
    safety_stocks: dict[str, int] = field(default_factory=dict)
    non_cost_metrics: dict[str, Any] = field(default_factory=dict)
    tolerance_pct_applied: Decimal | None = None
    checker_version: str = CHECKER_VERSION

    @property
    def valid(self):
        return self.accepted

    def model_dump(self, **kwargs):
        from dataclasses import asdict
        return asdict(self)


def safety_stock_units(item: dict) -> int:
    """C1, exact: smallest integer s >= 0 with s*s >= (z*std)^2 * lead_time."""
    from .schemas_v12 import Z_TABLE
    if item["safety_stock_override"] is not None:
        return item["safety_stock_override"]
    if item["service_level"] is None:
        return 0
    z = Fraction(str(Z_TABLE[Decimal(str(item["service_level"]))]))
    target = (z * Fraction(str(item["demand_std"]))) ** 2 * Fraction(str(item["lead_time_periods"]))
    s = 0
    while s * s < target:
        s += 1
    return s


def _net_requirements(w):
    tol = w["policy"]["late_inbound_tolerance_days"]
    credit = Decimal(str(w["policy"]["late_inbound_credit"]))
    net, safety = {}, {}
    for item in w["items"]:
        iid = item["item_id"]
        due = item["due_date"]
        limit = due + timedelta(days=tol)
        usable = sum(r["quantity"] for r in w["stock"] if r["item_id"] == iid and r["status"] == "usable")
        on_time = sum(r["quantity"] for r in w["inbound"] if r["item_id"] == iid and r["arrival_date"] <= due)
        late = sum(int((Decimal(r["quantity"]) * credit).to_integral_value(rounding=ROUND_FLOOR))
                   for r in w["inbound"] if r["item_id"] == iid and due < r["arrival_date"] <= limit)
        safety[iid] = safety_stock_units(item)
        net[iid] = max(0, item["demand"] + safety[iid] - usable - on_time - late)
    return net, safety


def _tolerance_pct(policy, reference: Decimal) -> Decimal:
    scale = Decimal(str(policy["cost_tolerance_reference_value"]))
    pct = Decimal(0)
    for tier in policy["cost_tolerance_tiers"]:
        if reference >= Decimal(str(tier["from_ratio"])) * scale:
            pct = Decimal(str(tier["pct"]))
    return pct


def verify(world: Any, submission: Any, expected_outcome: str | None = None,
           reference_cost: Decimal | str | None = None, task_measures: list[str] | None = None) -> VerificationResult12:
    from .schemas_v12 import World, parse_submission
    try:
        w = World.model_validate(world).model_dump(mode="json")
        s = parse_submission(submission).model_dump(mode="json")
    except (ValueError, TypeError) as exc:
        return VerificationResult12(False, "invalid", critical_failures=["schema_validation"],
                                    checks={"schema_validation": False}, evidence=[str(exc)])
    for item in w["items"]:
        item["due_date"] = _date.fromisoformat(item["due_date"])
    for row in w["inbound"]:
        row["arrival_date"] = _date.fromisoformat(row["arrival_date"])
    failures, evidence, checks = [], [], {}

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            failures.append(name)

    items = {i["item_id"]: i for i in w["items"]}
    suppliers = {v["supplier_id"]: v for v in w["suppliers"]}
    quotes = {(q["supplier_id"], q["item_id"]): q for q in w["quotes"]}
    net, safety = _net_requirements(w)
    arrival = {k: _date.fromisoformat(q["arrival_date"]) for k, q in quotes.items()}
    ok_quote = {k: q["qualified"] and q["valid_from"] <= w["as_of"] <= q["valid_to"]
                and arrival[k] <= items[k[1]]["due_date"] for k, q in quotes.items()}
    limit = w["constraints"]["approval_limit"]
    limit = None if limit is None else Decimal(str(limit))
    threshold = Decimal(str(w["policy"]["moq_excess_approval_threshold"]))
    granted = {(a["item_id"], a["approval_id"]) for a in w["approvals"] if a["kind"] == "moq_excess"}

    def estimate_unit_cost(q):
        parts = []
        for name in ("unit_price", "variable_freight"):
            v = q.get(name)
            if v is None:
                v = q.get("last_known_" + name)
            if v is None:
                return None
            parts.append(Decimal(str(v)))
        return parts[0] + parts[1]

    # C6: eligible quotes of needed items with a missing term, and whether the estimate path covers each.
    missing_quotes, blocking = {}, {}
    for (sid, iid), q in quotes.items():
        if not ok_quote[(sid, iid)] or net[iid] == 0:
            continue
        names = [n for n in ("unit_price", "variable_freight") if q.get(n) is None]
        if not names:
            continue
        missing_quotes[(sid, iid)] = [f"quotes.{sid}.{iid}.{n}" for n in names]
        cost = estimate_unit_cost(q)
        ref_qty = min(q["capacity"], max(net[iid], q["moq"]))
        covered = (cost is not None and not items[iid]["critical"] and limit is not None and ref_qty * cost <= limit)
        if not covered:
            blocking[(sid, iid)] = missing_quotes[(sid, iid)]
    # C5: approvals that would be needed because MOQ forces excess and none is on file for the item.
    approval_fields = set()
    for iid, item in items.items():
        if net[iid] == 0 or not item["moq_excess_allowed"]:
            continue
        sizes = [_order_sizes(q) for k, q in quotes.items() if k[1] == iid and ok_quote[k]]
        floor = _reachable_floor(sizes, net[iid])
        if floor is not None and floor > net[iid] + item["excess_allowance"] and not any(a[0] == iid for a in granted):
            approval_fields.add(f"approvals.moq_excess.{iid}")

    kind = s["kind"]
    if expected_outcome is not None:
        check("expected_outcome", kind == expected_outcome)
    if task_measures is not None:
        check("concentration_measure_declared", all(r["measure"] == "spend_share" or r["measure"] in task_measures
                                                    for r in w["constraints"]["concentration"]))
    base = dict(net_requirements=net, safety_stocks=safety)

    if kind in ("clarification", "infeasible"):
        check("exception_evidence", bool(s["evidence"]) and all(e.strip() for e in s["evidence"]))
        if kind == "clarification":
            askable = {f for fields in blocking.values() for f in fields} | approval_fields
            check("clarification_required", bool(askable))
            check("missing_field", s.get("field") in askable)
            check("clarification_escalated", s.get("disposition") == "record_and_escalate")
        else:
            deficits = []
            for iid in items:
                cap = sum(max(_order_sizes(q), default=0) for k, q in quotes.items() if k[1] == iid and ok_quote[k])
                if cap < net[iid]:
                    deficits.append(f"{iid}: eligible order capacity {cap} < net requirement {net[iid]}")
            check("capacity_certificate", bool(deficits))
            check("capacity_diagnosis", any("capacity" in e.lower() and any(t in e.lower() for t in ("less than", "shortfall", "<", "insufficient")) for e in s["evidence"]))
            evidence.extend(deficits)
        return VerificationResult12(not failures, kind, critical_failures=failures, checks=checks, evidence=evidence, **base)

    check("award_outcome", kind == "award")
    check("award_evidence", bool(s["evidence"]) and all(e.strip() for e in s["evidence"]))
    check("missing_term_clarification_first", not blocking)     # C6: never award around a gap the estimate path cannot cover
    totals = {iid: 0 for iid in items}
    lines = {}
    seen = set()
    cost_known = True
    estimated = []
    for idx, a in enumerate(s["allocations"]):
        sid, iid, qty = a["supplier_id"], a["item_id"], a["quantity"]
        pair = (sid, iid)
        prefix = f"allocation.{idx}"
        check(prefix + ".unique", pair not in seen)
        seen.add(pair)
        check(prefix + ".known", pair in quotes and sid in suppliers and iid in items)
        if pair not in quotes:
            continue
        totals[iid] += qty
        if not qty:
            continue
        q = quotes[pair]
        check(prefix + ".eligible", ok_quote[pair])
        check(prefix + ".capacity", qty <= q["capacity"])
        check(prefix + ".moq", qty >= q["moq"])
        check(prefix + ".multiple", qty % q["multiple"] == 0)
        terms, missing_names = [], []
        for name in ("unit_price", "variable_freight"):
            value = q.get(name)
            if value is None:
                missing_names.append(name)
                value = q.get("last_known_" + name)
            if value is None:
                cost_known = False
            else:
                terms.append(Decimal(str(value)))
        if len(terms) != 2:
            check(prefix + ".commercial_terms", False)
            continue
        unit_cost = terms[0] + terms[1]
        lines.setdefault(sid, []).append((iid, qty, unit_cost))
        if missing_names:
            estimated.append(f"{sid}:{iid}")
            check(prefix + ".estimate_not_critical", not items[iid]["critical"])
            check(prefix + ".estimate_within_approval_limit", limit is not None and qty * unit_cost <= limit)   # C4: at or below
            check(prefix + ".estimate_flagged", f"estimated:{sid}:{iid}" in s["flags"])
            check(prefix + ".estimate_clarification_requested",
                  all(f"quotes.{sid}.{iid}.{n}" in s["clarification_requests"] for n in missing_names))
    for iid, item in items.items():
        bought, need = totals[iid], net[iid]
        check(f"item.{iid}.shortfall", bought >= need)
        if bought > need + item["excess_allowance"]:
            sizes = [_order_sizes(q) for k, q in quotes.items() if k[1] == iid and ok_quote[k]]
            floor = _reachable_floor(sizes, need)
            justified = item["moq_excess_allowed"] and floor is not None and bought == floor
            check(f"item.{iid}.excess", justified)
            if justified:
                check(f"item.{iid}.moq_excess_flag", f"moq_excess:{iid}" in s["flags"])
                goods_item = sum((q * c for rows in lines.values() for i2, q, c in rows if i2 == iid), Decimal(0))
                excess_units = bought - need - item["excess_allowance"]
                if excess_units * goods_item > threshold * bought:    # excess value above the threshold
                    check(f"item.{iid}.moq_excess_approval", any((iid, ref) in granted for ref in s["approval_refs"]))
        if item["max_excess"] is not None:
            check(f"item.{iid}.shelf_life_cap", bought - need <= item["max_excess"])
    check("commercial_terms", cost_known)
    spend, total = {}, None
    if cost_known:
        for sid, rows in lines.items():
            goods = sum((q * c for _, q, c in rows), Decimal(0))
            charge = _tier_charge(suppliers[sid], sum(q for _, q, _ in rows), goods)
            spend[sid] = goods + charge
        total = sum(spend.values(), Decimal(0))
    gap = gap_pct = label = tol_applied = None
    metrics = {}
    if total is not None:
        try:
            claimed = Decimal(str(s["claimed_total_cost"]))
            check("claimed_cost", claimed.is_finite() and claimed == total)
        except Exception:
            check("claimed_cost", False)
        check("budget", total <= Decimal(str(w["constraints"]["budget"])))
        for n, rule in enumerate(w["constraints"]["concentration"]):
            lim = Decimal(str(rule["limit"]))
            name = f"concentration.{n}.{rule['measure']}"
            if rule["measure"] == "spend_share":
                check(name, total == 0 or all(v <= lim * total for v in spend.values()))
                continue
            scope = rule["item_ids"] if rule["item_ids"] is not None else list(items)
            units = {(sid, iid): q for sid, rows in lines.items() for iid, q, _ in rows if iid in scope}
            if rule["measure"] == "quantity_share":
                den = sum(units.values())
                per = {}
                for (sid, _), q in units.items():
                    per[sid] = per.get(sid, 0) + q
                check(name, den == 0 or all(v <= lim * den for v in per.values()))
            else:
                ok = True
                for iid in scope:
                    den = sum(q for (_, i), q in units.items() if i == iid)
                    ok = ok and all(q <= lim * den for (_, i), q in units.items() if i == iid)
                check(name, ok)
        if reference_cost is not None:
            ref = Decimal(str(reference_cost))
            gap = total - ref
            gap_pct = gap / ref if ref > 0 else None
            tol_abs = Decimal(str(w["policy"]["cost_tolerance_abs"]))
            tol_applied = _tolerance_pct(w["policy"], ref)
            if gap < 0:
                label = "below_reference"
            elif gap == 0:
                label = "optimal"
            elif gap <= tol_abs or gap <= tol_applied * ref:
                label = "equivalent_to_optimal"
            else:
                label = "suboptimal"
        weight = sum(q for rows in lines.values() for _, q, _ in rows)
        rel = {sid: suppliers[sid].get("reliability_score") for sid in lines}
        if weight and all(v is not None for v in rel.values()):
            wavg = sum(Decimal(str(rel[sid])) * q for sid, rows in lines.items() for _, q, _ in rows) / weight
            metrics["quantity_weighted_reliability"] = str(wavg.quantize(METRIC_PLACES))
            metrics["worst_reliability"] = str(min(Decimal(str(v)) for v in rel.values()))
        risks = [quotes[(sid, iid)].get("lead_time_risk") for sid, rows in lines.items() for iid, _, _ in rows]
        if risks and all(v is not None for v in risks):
            metrics["max_lead_time_risk"] = str(max(Decimal(str(v)) for v in risks))
        slack = [(items[iid]["due_date"] - arrival[(sid, iid)]).days for sid, rows in lines.items() for iid, _, _ in rows]
        if slack:
            metrics["min_arrival_slack_days"] = min(slack)
    return VerificationResult12(not failures, kind, total, failures, checks, evidence, gap, gap_pct, label,
                                estimated, net, safety, metrics, tol_applied)


verify_submission = verify
verify_award = verify
