"""Independent business checker; deliberately imports no optimizer code."""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CHECKER_VERSION = "1.0"
CENT = Decimal("0.01")

@dataclass
class VerificationResult:
    accepted: bool
    outcome: str
    independent_cost: Decimal | None = None
    critical_failures: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    objective_gap: Decimal | None = None
    checker_version: str = CHECKER_VERSION

    @property
    def valid(self):
        return self.accepted

    def model_dump(self, **kwargs):
        from dataclasses import asdict
        return asdict(self)


def _dict(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def verify(world: Any, submission: Any, expected_outcome: str | None = None,
           reference_cost: Decimal | str | None = None) -> VerificationResult:
    """Check awards independently; economic suboptimality does not invalidate feasibility.

    Infeasibility certificates currently cover a necessary item-capacity condition.
    Other infeasibility claims are conservatively rejected as unsupported.
    """
    from .schemas import World, parse_submission
    try:
        w = World.model_validate(world).model_dump(mode="json")
        s = parse_submission(submission).model_dump(mode="json")
    except (ValueError, TypeError) as exc:
        return VerificationResult(False, "invalid", critical_failures=["schema_validation"],
                                  checks={"schema_validation": False}, evidence=[str(exc)])
    failures, evidence = [], []
    checks = {}
    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            failures.append(name)
    check("schema_version", w.get("schema_version") == "1.0")
    items = {i["item_id"]: i for i in w["items"]}
    suppliers = {v["supplier_id"]: v for v in w["suppliers"]}
    quotes = {(q["supplier_id"], q["item_id"]): q for q in w["quotes"]}
    net = {}
    for iid, item in items.items():
        stock = sum(r["quantity"] for r in w.get("stock", []) if r["item_id"] == iid and r["status"] == "usable")
        inbound = sum(r["quantity"] for r in w.get("inbound", []) if r["item_id"] == iid and r["status"] == "committed" and str(r["arrival_date"]) <= str(item["due_date"]))
        net[iid] = max(0, item["demand"] - stock - inbound)
    def eligible(q):
        return q["qualified"] and str(q["valid_from"]) <= str(w["as_of"]) <= str(q["valid_to"]) and str(q["arrival_date"]) <= str(items[q["item_id"]]["due_date"])
    kind = s.get("kind", "")
    if expected_outcome is not None:
        check("expected_outcome", kind == expected_outcome)
    if kind in ("clarification", "infeasible"):
        check("exception_evidence", bool(s.get("evidence")) and all(isinstance(e, str) and e.strip() for e in s.get("evidence", [])))
        if kind == "clarification":
            missing = {f"quotes.{sid}.{iid}.{name}" for (sid, iid), q in quotes.items() for name in ("unit_price", "variable_freight") if q.get(name) is None}
            missing |= {f"suppliers.{sid}.fixed_charge" for sid, v in suppliers.items() if v.get("fixed_charge") is None}
            check("missing_field", s.get("field") in missing)
        else:
            deficits = []
            for iid in items:
                capacity = sum((q["capacity"] // q["multiple"]) * q["multiple"] for q in quotes.values() if q["item_id"] == iid and eligible(q) and (q["capacity"] // q["multiple"]) * q["multiple"] >= q["moq"])
                if capacity < net[iid]:
                    deficits.append(f"{iid}: eligible order capacity {capacity} < net requirement {net[iid]}")
            check("capacity_certificate", bool(deficits))
            check("capacity_diagnosis", any("capacity" in e.lower() and any(term in e.lower() for term in ("less than", "shortfall", "<", "insufficient")) for e in s.get("evidence", [])))
            evidence.extend(deficits)
        return VerificationResult(not failures, kind, critical_failures=failures, checks=checks, evidence=evidence)
    check("award_outcome", kind == "award")
    check("award_evidence", bool(s.get("evidence")) and all(e.strip() for e in s.get("evidence", [])))
    totals = {iid: 0 for iid in items}
    subtotal = {}
    selected = set()
    seen = set()
    cost_known = True
    for idx, a in enumerate(s.get("allocations", [])):
        sid, iid, qty = a.get("supplier_id"), a.get("item_id"), a.get("quantity")
        pair = (sid, iid)
        prefix = f"allocation.{idx}"
        check(prefix + ".unique", pair not in seen)
        seen.add(pair)
        check(prefix + ".known", pair in quotes and sid in suppliers and iid in items)
        integral = type(qty) is int and qty >= 0
        check(prefix + ".quantity", integral)
        if pair not in quotes or sid not in suppliers or iid not in items or not integral:
            continue
        check(prefix + ".unit", a.get("unit", items[iid]["unit"]) == items[iid]["unit"])
        totals[iid] += qty
        if not qty:
            continue
        q = quotes[pair]
        check(prefix + ".eligible", eligible(q))
        check(prefix + ".capacity", qty <= q["capacity"])
        check(prefix + ".moq", qty >= q["moq"])
        check(prefix + ".multiple", qty % q["multiple"] == 0)
        selected.add(sid)
        if q.get("unit_price") is None or q.get("variable_freight") is None:
            cost_known = False
        else:
            subtotal[sid] = subtotal.get(sid, Decimal(0)) + qty * (Decimal(str(q["unit_price"])) + Decimal(str(q["variable_freight"])))
    for iid, item in items.items():
        check(f"item.{iid}.coverage", net[iid] <= totals[iid] <= net[iid] + item["excess_allowance"])
    for sid in selected:
        if suppliers[sid].get("fixed_charge") is None:
            cost_known = False
        else:
            subtotal[sid] = (subtotal.get(sid, Decimal(0)) + Decimal(str(suppliers[sid]["fixed_charge"]))).quantize(CENT, rounding=ROUND_HALF_UP)
    check("commercial_terms", cost_known)
    total = sum(subtotal.values(), Decimal("0.00")) if cost_known else None
    gap = None
    if total is not None:
        try:
            claimed = Decimal(str(s.get("claimed_total_cost")))
            check("claimed_cost", claimed.is_finite() and claimed == total)
        except Exception:
            check("claimed_cost", False)
        budget = w["constraints"].get("budget")
        check("budget", budget is None or total <= Decimal(str(budget)))
        limit = w["constraints"].get("concentration_limit")
        check("concentration", limit is None or total == 0 or all(v <= total * Decimal(str(limit)) for v in subtotal.values()))
        if reference_cost is not None:
            ref = Decimal(str(reference_cost))
            if ref > 0:
                gap = (total - ref) / ref
            elif ref == 0 and total == 0:
                gap = Decimal(0)
    return VerificationResult(not failures, kind, total, failures, checks, evidence, gap)

verify_submission = verify
verify_award = verify
