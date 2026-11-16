# Supplier allocation rules 1.1 (repair A1 to A7, issue #35)

**Status.** Implemented: yes. Tested: yes (arithmetic and independent enumeration). Reviewed by a practitioner: **no; awaiting re-review.** The only review so far is the owner-practitioner review of 2026-11-16, which is not independent and confirmed no numeric value. Every number in the 1.1 fixtures is **PROVISIONAL, needs practitioner value** (see [the provisional-values table](../acceptance/static-v1.1-provisional-values.md)). Nothing here is a claim about real practice or about model ability.

Version 1.0 ([supplier-allocation.md](supplier-allocation.md), `schemas.py`, `verification.py`, `solvers.py`, `fixtures/reference_cases/`) is unchanged and still reproducible. 1.1 lives beside it: `schemas_v11.py`, `verification_v11.py`, `solvers_v11.py`, `fixtures/reference_cases_v1_1/`. Schema, policy and checker versions are all `1.1`; a 1.0 world is rejected by the 1.1 schema and vice versa.

## Rules

| Finding | Rule 1.1 |
| --- | --- |
| A1 net requirement | `net = max(0, demand + safety_stock - usable - on-time inbound - late credit)`. On-time means arrival on or before the item deadline. Late credit: an inbound line arriving 1 to `late_inbound_tolerance_days` days after the deadline (inclusive) counts `floor(quantity x late_inbound_credit)` units; later arrivals count nothing. Held and reserved stock never counts. Tolerance never applies to new supplier orders, which must still arrive by the deadline. |
| A2 concentration | `constraints.concentration` is a list of rules; each task declares the measures that apply. `spend_share`: supplier landed spend (fixed charge included) over total landed spend. `quantity_share`: supplier units over total units, summed only over the rule's named items. `per_item_share`: supplier units of an item over that item's total units, for each in-scope item. Comparison is exact multiplication; a zero denominator passes. |
| A3 optimality | Feasibility is separate from quality. Label: `optimal` (gap 0), `equivalent_to_optimal` (gap <= `cost_tolerance_abs` or <= `cost_tolerance_pct` x optimum, inclusive), else `suboptimal`. The exact absolute gap and ratio are always reported. Supplier `reliability_score`, quote `lead_time_risk` and arrival slack days are reported as separate metrics and never merged into cost or into pass/fail. |
| A4 missing price or freight | Never substitute zero. The agent must request the field first (`clarification_requests`). If the line value `qty x (price + freight)` using last known terms is strictly under `approval_limit` and the item is not critical, an award is allowed and must carry the flag `estimated:<supplier>:<item>`. Otherwise (no last known value, critical part, or value not under the limit) the correct submission is a `clarification` with `disposition: record_and_escalate`. |
| A5 fixed charge, rounding | A supplier's fixed charge is flat or table-driven by order units or goods value (largest lower bound not above the measure, inclusive). **All per-supplier rounding is removed**: totals are exact Decimal sums, compared exactly (claimed cost, budget, band, shares). v1.0 rounded each supplier subtotal half-up to cents; the two disagree on `ref-21`. |
| A6 excess | Excess beyond `excess_allowance` is allowed only if the item sets `moq_excess_allowed`, the bought total equals the smallest quantity at or above net that valid order sizes can reach (so MOQ and multiples force it), and the award carries `moq_excess:<item>`. `max_excess` (shelf life or obsolescence) caps all excess, including the explicit allowance. |

Infeasibility remains supported only by the eligible order capacity certificate (net requirement now includes safety stock). Other infeasibility claims are rejected as unsupported.

## Why 1.0 and 1.1 differ on rounding (ref-21)

Quotes 1.0041 and 1.0045 for 4 units. Version 1.0 rounds each supplier subtotal to cents: single-supplier awards both cost 4.02, and the split A3+B1 rounds to 3.01 + 1.00 = 4.01, an artifact cheaper than either. In 1.1 A4 = 4.0164, B4 = 4.0180 and the split is 4.0168, so A alone is strictly optimal. A claim of 4.02 is rejected.

## Independence

`verification_v11.py` imports only the 1.1 schema. `solvers_v11.py` shares no logic with it. `tests/test_reference_cases_v1_1.py` imports no production code and enumerates every quantity vector of each tiny case, re-deriving net requirement, floors, tiers, shares and flags from the rules above. `tests/test_static_v11.py` checks the production checker and solver against the fixtures and each rule.

## Reference cases

Each JSON has a hand calculation, the expected submission, known wrong submissions with the defect, and at least one alternative valid answer with its status. Cases 01 to 10 are the v1.0 diagnostics re-tuned; 11 to 22 are new.

| Case | Diagnostic | Hand result |
| --- | --- | --- |
| ref-01 | basic award, safety stock, late credit | net 10+3-2-1-2 = 8, cost 16.00 |
| ref-02 | fixed charge tradeoff, equivalent band | B 8.00; A 8.40 equivalent |
| ref-03 | MOQ and multiple with safety stock | net 5, A4+B1 = 6.00 |
| ref-04 | arrival deadline, lead-time metric | B 8.00; C 8.16 on the band edge |
| ref-05 | qualification and ties | 8.00, three tied awards |
| ref-06 | spend-share concentration | 4.00, any split with at most 2 each |
| ref-07 | binding budget, exact decimals | A4 4.040, tie with C |
| ref-08 | MOQ-justified flagged excess | A4 4.00 with `moq_excess` |
| ref-09 | missing term, no last known | clarify and escalate (two valid fields) |
| ref-10 | capacity with safety stock | 3 < net 4, infeasible |
| ref-11 | late credit window, floor | net 3, cost 6.00 |
| ref-12 | safety stock with stock above demand | X net 2, Y net 2, cost 4.00 |
| ref-13 | quantity share only | 8.80; spend share would reject it |
| ref-14 | per-item share | 9.00, three tied awards |
| ref-15 | spend share with fixed charge, equality | 5.00, A share exactly 0.60 |
| ref-16 | equivalence band, separate metrics | A 50.00; B 50.40 equivalent; C 52.00 suboptimal |
| ref-17 | estimated-price path | A 9.00 flagged estimated; B 9.20 equivalent |
| ref-18 | critical part escalates | clarification despite value 9.00 |
| ref-19 | high value escalates | line 90.00 not under 50.00, clarification |
| ref-20 | varying fixed charge tiers | A6 = 6.00 + 2.00 = 8.00 |
| ref-21 | v1.0 rounding versus 1.1 exact | A 4.0164 optimal; 1.0 says 4.01 by split |
| ref-22 | shelf-life cap | A4 6.40; C6 6.00 rejected by cap |

## Open for the reviewer

All numeric values, the structural choices listed in the provisional-values table, and the re-review itself. Issue #35 stays open until re-review is recorded.
