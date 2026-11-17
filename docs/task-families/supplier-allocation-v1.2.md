# Supplier allocation rules 1.2 (owner-practitioner re-review, issue #35)

**Status.** Implemented: yes. Tested: yes (arithmetic, independent enumeration, production checker and solver). Reviewed by a practitioner: no; awaiting re-review of this version. The only reviews so far are the owner-practitioner review of 2026-11-16 and the re-review round 2 of 2026-11-17 ([record](../reviews/2026-11-17-practitioner-re-review-17.md)); both are **not independent**, and neither confirmed a point value. Every number in the 1.2 fixtures is **PROVISIONAL, needs practitioner value** (see [the provisional-values table](../acceptance/static-v1.2-provisional-values.md), which has a "changed from v1.1" column). Nothing here is a claim about real practice or about model ability.

Versions 1.0 and 1.1 ([supplier-allocation.md](supplier-allocation.md), [supplier-allocation-v1.1.md](supplier-allocation-v1.1.md), their schemas, checkers, solvers and fixtures) are unchanged and still reproducible. 1.2 lives beside them: `schemas_v12.py`, `verification_v12.py`, `solvers_v12.py`, `fixtures/reference_cases_v1_2/`. Schema, policy and checker versions are all `1.2`; a 1.1 world is rejected by the 1.2 schema and vice versa. Small helpers that did not change (order sizes, reachable floor, fixed-charge tiers, unit cost) are imported from the 1.1 modules; the rules that changed are re-implemented in the 1.2 modules.

## Rules (re-review answers C1 to C8)

| Id | Reviewer answer | Rule 1.2 | Changed from 1.1 |
| --- | --- | --- | --- |
| C1 safety stock | Service-level based | `SS = ceil(z(service_level) x demand_std x sqrt(lead_time_periods))` with a fixed z-table (0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263). Exact: SS is the smallest integer `s` with `s x s >= (z x std)^2 x lead_time`, so there is no float and no rounding noise (z x std x sqrt(lead) = 49 exactly gives 49, not 50). Each item declares `service_level`, `demand_std` (per period) and `lead_time_periods` together or not at all; `safety_stock_override` replaces the computed value. `net = max(0, demand + SS - usable - on-time inbound - late credit)`. Provisional level 0.95. | Direct safety-stock quantity replaced by service-level inputs; override kept |
| C2 late inbound | 50% within 2 to 3 days | Unchanged mechanism: arrival 1 to `late_inbound_tolerance_days` days late (inclusive) counts `floor(quantity x 0.50)` units; later counts nothing; never applies to new orders. Provisional window 3 days. | Window value 3 (fixtures had 0, 2 or 3) |
| C3 cost tolerance | Scales with order size | Equivalent-to-optimal if gap <= `cost_tolerance_abs` or gap <= `tier pct x optimum`. Tiers are keyed on `optimum / cost_tolerance_reference_value` (inclusive lower bounds): 0: 3%, 0.5: 2%, 5: 1%. With the provisional reference value 100.00 that is 3% below 50, 2% from 50 to under 500, 1% from 500 up. Schema rule: `pct` never increases with the bound, so larger orders never get a looser tolerance. The exact gap and ratio are still always reported. | One fixed fraction replaced by tiers |
| C4 approval limit | 1,000 to 10,000; at or below | An estimate on last known terms is allowed when the line value `qty x (price + freight)` is **at or below** the approval limit (provisional 5,000.00) and the item is not critical. It carries `estimated:<supplier>:<item>` and requests the missing field. Above the limit, or critical, or no last known value: escalate. | Boundary was strictly under; limit was 50.00 |
| C5 MOQ excess | Needs approval; threshold not given | Excess beyond the allowance is acceptable only when the item allows it, the total equals the smallest reachable quantity at or above net, and it is flagged `moq_excess:<item>`. If the excess value (`excess units x item goods value / units bought`) is **above** the threshold (provisional 500.00, reviewer gave none), the submission must also cite a granted approval record (`approval_refs`) for the item from `world.approvals`. At or below the threshold the flag alone suffices. With no approval on file the supported answer is a clarification asking for `approvals.moq_excess.<item>`, with escalation. `max_excess` still caps everything. | Approval requirement and threshold are new |
| C6 missing term | Ask clarification first | If an eligible quote for a needed item has a missing price or freight and the estimate path does not cover it, **no award is acceptable**, even when other complete quotes could cover the need; the answer is a `clarification` with `record_and_escalate`. The estimate path covers a quote when the item is non-critical, last known terms exist, and `min(capacity, max(net, MOQ)) x estimated unit cost` is at or below the approval limit. Where it covers, an estimate award or an award around that quote is allowed. Items with zero net requirement are ignored. | 1.1 awarded around the gap; 1.2 restores the 1.0 behaviour |
| C7 concentration | Spend share by default | `spend_share` is the default measure. `quantity_share` and `per_item_share` are applied only when the task declares them (`Task.concentration_measures`, checked by `check_task_world` and by `verify(..., task_measures=...)`). Comparisons exact; a zero denominator passes. | Non-spend measures now need a task declaration |
| C8 rounding | Stays removed | Exact Decimal everywhere; claimed cost, budget, band and shares compare exactly. | Unchanged |

Infeasibility remains supported only by the eligible order capacity certificate (net requirement includes safety stock).

## Reference cases

33 fixtures in `fixtures/reference_cases_v1_2/`, built by `scripts/build_static_v12_fixtures.py` from the frozen 1.1 fixtures plus eleven new cases. Each JSON has a hand calculation, the expected submission, known wrong submissions with the defect, at least one alternative valid answer with its status, and a `changed_from_v1_1` list. Cases 01 to 22 are the 1.1 cases re-tuned (same diagnostics, new rules applied); 23 to 33 are new.

| Case | Diagnostic | Hand result |
| --- | --- | --- |
| ref-01 | service-level safety stock, late credit at the 3-day edge | SS ceil(1.6449 x sqrt 2) = 3, net 8, cost 16.00 |
| ref-02 | fixed charge tradeoff, equivalent band | B 8.00; A 8.40 equivalent |
| ref-03 | MOQ and multiple with service-level safety stock | SS 2, net 5, A4+B1 = 6.00 |
| ref-04 | arrival deadline, 3% tier band edge | B 8.00; C 8.24 on the band edge |
| ref-05 | qualification and ties | 8.00, three tied awards |
| ref-06 | spend-share concentration (default measure) | 4.00 |
| ref-07 | binding budget, exact decimals | A4 4.040, tie with C |
| ref-08 | MOQ excess below the approval threshold: flag only | A4 4.00 with `moq_excess` |
| ref-09 | missing term, no last known | clarify and escalate |
| ref-10 | capacity with service-level safety stock | 3 < net 4, infeasible |
| ref-11 | late credit window, floor | net 3, cost 6.00 |
| ref-12 | safety stock with stock above demand | X net 2, Y net 2, cost 4.00 |
| ref-13 | quantity share, task-declared | 8.80 |
| ref-14 | per-item share, task-declared | 9.00 |
| ref-15 | spend share with fixed charge, equality | 5.00 |
| ref-16 | 2% tier at exactly 50.00, separate metrics | A 50.00; B 50.40 equivalent; C 52.00 suboptimal |
| ref-17 | estimate path covers A; award around also allowed | A 9.00 estimated; B 9.20 equivalent |
| ref-18 | critical part escalates | clarification |
| ref-19 | high value escalates (5,200.00 > 5,000.00) | clarification |
| ref-20 | varying fixed charge tiers | A6 = 8.00 |
| ref-21 | exact arithmetic; tolerance tiers set to 0% | A 4.0164 optimal |
| ref-22 | shelf-life cap | A4 6.40 |
| ref-23 | service level 97.5%: ceil(9.8) = 10 | net 11, A11 22.00 |
| ref-24 | exact integer 49 (no extra unit) | net 50, A50 50.00 |
| ref-25 | tolerance tier 3% (optimum 49.00) | B 50.47 on the edge, equivalent |
| ref-26 | tolerance tier 1% at exactly 500.00 | B 505.00 on the edge; C 505.04 suboptimal |
| ref-27 | tolerance tier 2% at 499.00 | B 508.98 on the edge |
| ref-28 | estimate exactly at the 5,000.00 limit is allowed | A40 5,000.00 estimated |
| ref-29 | estimate 5,000.40 escalates although B and C are complete | clarification |
| ref-30 | ask first, critical part, complete alternative exists | clarification |
| ref-31 | MOQ excess 600.00 with approval APR-7 on file | A20 6,000.00 with flag and APR-7 |
| ref-32 | same world, no approval on file | request approval and escalate |
| ref-33 | MOQ excess exactly 500.00 | A20 5,000.00 flag only |

## Independence

`verification_v12.py` imports only the 1.2 schema (plus three small 1.1 helper functions for order sizes, reachable floor and fixed-charge tiers); it shares no logic with `solvers_v12.py`. Safety stock is computed by two different methods: the checker uses Fraction arithmetic and an integer search, the solver uses a high-precision Decimal square root, and a test compares them over a grid. `tests/test_reference_cases_v1_2.py` imports no production code, computes safety stock a third way, and enumerates every quantity vector of each case, re-deriving net requirement, tiers, approval need, ask-first and flags from the rules above. `tests/test_static_v12.py` checks the production checker, solver and schema against the fixtures and each rule.

## Known limits

- The checker accepts a request for `approvals.moq_excess.<item>` whenever MOQ forces excess for an item with no approval on file; it does not decide whether the excess value would exceed the threshold. A task that expects an award from such a world is still graded by its expected outcome.
- "Awarding around" a gap is judged per quote by the estimate-path test above, using the net requirement; an award that mixes a covered estimate with complete quotes is accepted.
- Approval records are modeled as granted records visible in the world; there is no multi-turn approval workflow.

## Open for the reviewer

All numeric values (service level, z-table use, window 2 or 3 days, tier constants and reference value, approval limit inside 1,000 to 10,000, MOQ approval threshold), the structural choices in the provisional-values table, and the re-review itself. #35 stays open until a re-review of 1.2 is recorded.
