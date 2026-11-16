# Practitioner review record for issue #17

Date: 2026-11-16
Reviewer: Supply chain practitioner, project owner (role only, by the reviewer's choice).
Independence: **Not independent.** The reviewer is also the project owner who commissioned this work. Treat this as owner-practitioner feedback, not external validation.
Format: interactive multiple-choice questions answered in the working session. Free-text answers are quoted exactly. Selections without free text are recorded as selected. The reviewer saw each rule as written in `docs/acceptance/dynamic-supplier-delay-v0.1.md` and `docs/task-families/supplier-allocation.md`, and did not review each generated case or the solver output. No sealed or generated development sample was reviewed.

## Decision

**Repair, then re-review.** Neither the static supplier-allocation family nor the S01 dynamic scenario is accepted as ready for model evaluation or teacher collection. Issue #17 stays open until the repairs below are made and the reviewer re-reviews them.

## Findings: dynamic scenario S01

| # | Rule reviewed | Reviewer answer | Required repair |
|---|---|---|---|
| S1 | Expedite USD24 flat; alternate 8 units for USD40 | "Need to understand the downsides and upsides cost is not just the only factor, service level, priority and impact equally important" | Do not judge options on cost alone. Report cost, service level, priority and impact as separate metrics. The two prices were not confirmed or corrected. |
| S2 | Penalty USD10 per undelivered unit at each close of days 3 to 5 | "Penalty can scale based on percentage fixed value per unit depending on contract and terms" | Make penalty a contract term: percent of order value, fixed per unit, or other, set per scenario. |
| S3 | Surplus components from the alternate order have zero value | Selected: add salvage or reuse value | Add a salvage or reuse value for leftover stock. Rate unspecified. |
| S4 | Scorecard dimensions | Selected all four: service level (OTIF), order priority or tier, downstream impact, supply risk afterwards | Report these alongside cost. Do not collapse into one number. |
| S5 | Backlog with partial delivery and no lost sales | Selected: depends on customer tier | Backlog versus cancellation behavior depends on customer tier. |
| S6 | One exclusive recovery choice on day 1 | "2 and 3": allow combinations and later revisits | Allow combined recovery actions and revisiting recovery on later days at changing cost. |
| S7 | Delay visible only at day 1 opening | Selected: add several scenarios | Build a family mixing sudden and warned disruptions. |

## Findings: static supplier allocation

| # | Rule reviewed | Reviewer answer | Required repair |
|---|---|---|---|
| A1 | Net requirement excludes held and late stock | "2 and 3": count safety stock, and give partial credit for late inbound | Add a safety stock target to net requirement. Allow late inbound to count within a tolerance window. Safety stock level and tolerance are unspecified. |
| A2 | Concentration is spend share including fixed charges | Selected: spend, quantity and per-item share | Support all three concentration measures. Which applies to which task is unspecified. |
| A3 | Zero cost tolerance for optimality | "2 and 3": small tolerance, and add non-cost factors | Add a small tolerance band and weigh non-cost factors such as supplier reliability or lead-time risk. Tolerance size unspecified. |
| A4 | Missing price or freight: clarify and escalate, never assume zero | "First request and escalate depending on value, if it's under the required approval limit and small order then can use last known price, if it's high and critical part then escalte" | Value-tiered policy: always request first. Under the approval limit and small order, allow last known price (flagged). High value or critical part: escalate. Approval limit unspecified. |
| A5 | Fixed supplier charge once per supplier; supplier subtotal rounded half-up to cents | "Fix charge varies and keep as is no rounding" | **Ambiguous, needs the reviewer to clarify.** "Fix charge varies" is clear: fixed charges can vary (for example by order size or freight tier). "keep as is no rounding" can mean keep the per-supplier rounding as is, or remove rounding. Not changed until clarified. |
| A6 | MOQ never justifies excess | "2 and 3": MOQ may justify excess with a flag, and shelf life limits excess | Allow buying to MOQ with a flag. Add shelf life or obsolescence limits on excess. |
| A7 | Ten reference cases | "All looks plausible but need more tuning" | Tune the ten cases to the changes above. No case was named as wrong. The reviewer did not individually review each case's numbers. |

## What this review does not establish

- It does not validate any numeric value (prices, rates, thresholds, tolerances). None were confirmed or corrected.
- It does not review generated development cases, solver outputs, graders or known-wrong submissions. The issue still requires those.
- It is not an independent review.
- It does not show that the family or scenario matches practice. It shows the owner-practitioner wants the changes above before evaluation.

## Open items

1. Clarify A5 (rounding).
2. Provide values for: safety stock level, late-inbound tolerance window, cost tolerance, approval limit, salvage rate, penalty terms by contract, tier definitions.
3. Re-review after repair.
