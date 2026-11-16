"""Independent business checker for static rules 1.1; imports no solver code.

Rules (all numeric parameters in fixtures are PROVISIONAL, see docs/acceptance):
  A1 net = max(0, demand + safety_stock - usable - on-time inbound - late credit); late inbound
     arriving 1..tolerance days after the item deadline earns floor(quantity * credit) units.
  A2 concentration rules name their measure(s); comparisons are exact Decimal multiplications.
  A3 optimality label optimal / equivalent_to_optimal / suboptimal; exact gap always reported;
     reliability and lead-time risk are separate report-only metrics, never merged with cost.
  A4 missing price/freight: clarify first; award on last known price only if line value is below the
     approval limit and the item is not critical, flagged 'estimated'. Never zero.
  A5 fixed charge may be table-driven; NO rounding anywhere; exact Decimal totals.
  A6 MOQ may justify excess beyond the allowance when flagged; max_excess caps all excess.
"""
from dataclasses import dataclass, field
from datetime import date as _date, timedelta
from decimal import Decimal, ROUND_FLOOR
from typing import Any

CHECKER_VERSION = "1.1"
METRIC_PLACES = Decimal("0.0001")


@dataclass
class VerificationResult11:
    accepted: bool
    outcome: str
    independent_cost: Decimal | None = None
    critical_failures: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    objective_gap: Decimal | None = None          # absolute, exact
    objective_gap_pct: Decimal | None = None      # exact ratio, omitted when optimum is zero
    optimality: str | None = None                 # optimal | equivalent_to_optimal | suboptimal | below_reference
    estimated_lines: list[str] = field(default_factory=list)
    net_requirements: dict[str, int] = field(default_factory=dict)
    non_cost_metrics: dict[str, Any] = field(default_factory=dict)
    checker_version: str = CHECKER_VERSION

    @property
    def valid(self):
        return self.accepted

    def model_dump(self, **kwargs):
        from dataclasses import asdict
        return asdict(self)


def _net_requirements(w):
    tol = w["policy"]["late_inbound_tolerance_days"]
    credit = Decimal(str(w["policy"]["late_inbound_credit"]))
    net = {}
    for item in w["items"]:
        iid = item["item_id"]
        due = item["due_date"]
        limit = due + timedelta(days=tol)
        usable = sum(r["quantity"] for r in w["stock"] if r["item_id"] == iid and r["status"] == "usable")
        on_time = sum(r["quantity"] for r in w["inbound"] if r["item_id"] == iid and r["arrival_date"] <= due)
        late = sum(int((Decimal(r["quantity"]) * credit).to_integral_value(rounding=ROUND_FLOOR))
                   for r in w["inbound"] if r["item_id"] == iid and due < r["arrival_date"] <= limit)
        net[iid] = max(0, item["demand"] + item["safety_stock"] - usable - on_time - late)
    return net


def _order_sizes(q):
    top = (q["capacity"] // q["multiple"]) * q["multiple"]
    return [m for m in range(q["multiple"], top + 1, q["multiple"]) if m >= q["moq"]]


def _reachable_floor(sizes_per_quote, net):
    """Smallest total at or above net reachable with one order size (or none) per quote."""
    if net == 0:
        return 0
    bound = net + max((max(s) for s in sizes_per_quote if s), default=0)
    reach = {0}
    for sizes in sizes_per_quote:
        reach |= {r + s for r in reach for s in sizes if r + s <= bound}
    above = [r for r in reach if r >= net]
    return min(above) if above else None


def _tier_charge(supplier, units, goods_value):
    if supplier["fixed_charge_basis"] == "flat":
        return Decimal(str(supplier["fixed_charge"]))
    measure = Decimal(units) if supplier["fixed_charge_basis"] == "order_units" else goods_value
    charge = None
    for tier in supplier["fixed_charge_table"]:
        if Decimal(str(tier["from_measure"])) <= measure:
            charge = Decimal(str(tier["charge"]))
    return charge


def verify(world: Any, submission: Any, expected_outcome: str | None = None,
           reference_cost: Decimal | str | None = None) -> VerificationResult11:
    from .schemas_v11 import World, parse_submission
    try:
        w = World.model_validate(world).model_dump(mode="json")
        s = parse_submission(submission).model_dump(mode="json")
    except (ValueError, TypeError) as exc:
        return VerificationResult11(False, "invalid", critical_failures=["schema_validation"],
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
    net = _net_requirements(w)
    arrival = {k: _date.fromisoformat(q["arrival_date"]) for k, q in quotes.items()}
    ok_quote = {k: q["qualified"] and q["valid_from"] <= w["as_of"] <= q["valid_to"]
                and arrival[k] <= items[k[1]]["due_date"] for k, q in quotes.items()}
    kind = s["kind"]
    if expected_outcome is not None:
        check("expected_outcome", kind == expected_outcome)
    base = dict(net_requirements=net)

    if kind in ("clarification", "infeasible"):
        check("exception_evidence", bool(s["evidence"]) and all(e.strip() for e in s["evidence"]))
        if kind == "clarification":
            missing = {f"quotes.{sid}.{iid}.{name}" for (sid, iid), q in quotes.items() if ok_quote[(sid, iid)]
                       for name in ("unit_price", "variable_freight") if q.get(name) is None}
            check("missing_field", s.get("field") in missing)
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
        return VerificationResult11(not failures, kind, critical_failures=failures, checks=checks, evidence=evidence, **base)

    check("award_outcome", kind == "award")
    check("award_evidence", bool(s["evidence"]) and all(e.strip() for e in s["evidence"]))
    totals = {iid: 0 for iid in items}
    lines = {}          # supplier -> list of (item, qty, unit_cost)
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
                cost_known = False          # never substitute zero
            else:
                terms.append(Decimal(str(value)))
        if len(terms) != 2:
            check(prefix + ".commercial_terms", False)
            continue
        unit_cost = terms[0] + terms[1]
        lines.setdefault(sid, []).append((iid, qty, unit_cost))
        if missing_names:
            estimated.append(f"{sid}:{iid}")
            limit = w["constraints"]["approval_limit"]
            check(prefix + ".estimate_not_critical", not items[iid]["critical"])
            check(prefix + ".estimate_under_approval_limit", limit is not None and qty * unit_cost < Decimal(str(limit)))
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
        if item["max_excess"] is not None:
            check(f"item.{iid}.shelf_life_cap", bought - need <= item["max_excess"])
    check("commercial_terms", cost_known)
    spend, total = {}, None
    if cost_known:
        for sid, rows in lines.items():
            goods = sum((q * c for _, q, c in rows), Decimal(0))
            charge = _tier_charge(suppliers[sid], sum(q for _, q, _ in rows), goods)
            spend[sid] = goods + charge
        total = sum(spend.values(), Decimal(0))        # exact: no rounding anywhere (A5)
    gap = gap_pct = label = None
    metrics = {}
    if total is not None:
        try:
            claimed = Decimal(str(s["claimed_total_cost"]))
            check("claimed_cost", claimed.is_finite() and claimed == total)
        except Exception:
            check("claimed_cost", False)
        check("budget", total <= Decimal(str(w["constraints"]["budget"])))
        for n, rule in enumerate(w["constraints"]["concentration"]):
            limit = Decimal(str(rule["limit"]))
            name = f"concentration.{n}.{rule['measure']}"
            if rule["measure"] == "spend_share":
                check(name, total == 0 or all(v <= limit * total for v in spend.values()))
                continue
            scope = rule["item_ids"] if rule["item_ids"] is not None else list(items)
            units = {(sid, iid): q for sid, rows in lines.items() for iid, q, _ in rows if iid in scope}
            if rule["measure"] == "quantity_share":
                den = sum(units.values())
                per = {}
                for (sid, _), q in units.items():
                    per[sid] = per.get(sid, 0) + q
                check(name, den == 0 or all(v <= limit * den for v in per.values()))
            else:
                ok = True
                for iid in scope:
                    den = sum(q for (_, i), q in units.items() if i == iid)
                    ok = ok and all(q <= limit * den for (_, i), q in units.items() if i == iid)
                check(name, ok)
        if reference_cost is not None:
            ref = Decimal(str(reference_cost))
            gap = total - ref
            gap_pct = gap / ref if ref > 0 else None
            tol_abs = Decimal(str(w["policy"]["cost_tolerance_abs"]))
            tol_pct = Decimal(str(w["policy"]["cost_tolerance_pct"]))
            if gap < 0:
                label = "below_reference"
            elif gap == 0:
                label = "optimal"
            elif gap <= tol_abs or gap <= tol_pct * ref:
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
    return VerificationResult11(not failures, kind, total, failures, checks, evidence, gap, gap_pct, label,
                                estimated, net, metrics)


verify_submission = verify
verify_award = verify
