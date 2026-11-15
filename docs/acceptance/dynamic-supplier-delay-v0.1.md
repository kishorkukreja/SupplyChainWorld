# Proposed acceptance scenario: supplier delay in an operating manufacturer

ID: DYN-ACCEPT-01 · Version: 0.1 · Date: 2026-11-15
Status: **Proposal for user review. Not an approved implementation specification.**

This is the first proposed observable demonstration of the [vision](../../vision.md), following the [alignment audit](../audits/2026-11-15-alignment-audit.md). It is intentionally small. Passing it demonstrates one dynamic episode, not a realistic general supply-chain benchmark or a useful training corpus.

## 1. Behavior to demonstrate

A manufacturer operates for five simulated days. A supplier delay threatens a customer delivery. The agent discovers the delay, chooses a recovery action, releases production over multiple days, observes actual receipts/completions, and sees the resulting service, inventory and costs.

The environment executes business transitions. Submitting a recommendation or incrementing a tool-call counter cannot satisfy this scenario.

All quantities, dates-as-day-indices, prices and rules below are assistant proposals requiring review. No practitioner signoff is claimed.

## 2. Small world and explicit assumptions

| Entity/rule | Proposed value |
|---|---|
| Manufacturer | One factory and one warehouse, treated as one inventory location |
| Product | One finished product P requiring one component C per unit |
| Initial state, opening day 1 | 4 C on hand; 0 finished P; no work in progress |
| Production | Up to 4 P per day; consumes 1 C per P; completes that day's accepted release at day close |
| Customer order | 12 P due at the close of day 3; partial deliveries allowed |
| Primary supplier order | Existing confirmed PO for 8 C; initially expected opening day 2 |
| Disruption | Opening day 1: supplier announces arrival moved to opening day 4 |
| Expedited recovery | Pay USD24 once on day1 to restore that existing PO's arrival to opening day2 |
| Alternate supplier | Buy 8 C for USD40 once on day1; delivery opening day2; primary PO still arrives day4 |
| Recovery budget | USD40 of incremental response spend; commitments consume budget immediately |
| Shipping | Automatic at day close on days3–5, after production, up to remaining customer quantity |
| Unfulfilled quantities | Backlogged through day5; no lost sales |
| Service penalty | USD10 per unit still undelivered at each assessment: closes of days3,4,5 |
| Decision cost | Incremental response spend plus those explicitly assessed service penalties |
| Existing primary PO cost | Already committed, identical across policies; excluded from incremental response comparison and recorded separately if shown |
| Other costs | No holding cost, taxes, FX, yield loss or setup charge in this toy case |

The penalty assessment schedule is deliberate: a shortfall at the day3 deadline incurs its first assessment at that close. Do not silently reinterpret it as a conventional elapsed-day penalty. Report the unmet units at each assessment.

## 3. Information boundary

At reset the agent receives the customer order, opening inventory, capacity/BOM rules, recovery budget, accessible tool definitions and initial confirmed arrival. The day1 delay notice becomes visible only when that event is processed. Recovery offers and their deadlines are discoverable through tools before the agent chooses.

The simulator holds the event calendar and deterministic supplier mechanics. It does not expose a preferred action, reference policy score, future hidden state, grader assertions or baseline answer. Only future terms actually promised to the agent (such as quoted arrival dates) may be visible. For this first deterministic case, no other surprise events occur.

Training/evaluation partition metadata is outside agent context. This public acceptance fixture is an engineering test case, never a sealed benchmark item.

## 4. Clock, events and actions

Each day has an explicit opening state, action phase and close:
1. Opening: apply scheduled receipts, then notices due at that opening; emit a new observable state.
2. Action phase: allow eligible recovery commitments, record the chosen production release, and inspect evidence.
3. Close: execute the accepted production release, consume components, produce finished goods, ship if day3 or later, assess any service penalty, then advance to the next opening.
4. Closing day5 terminates the episode and produces a scorecard.

Recovery choice is exclusive: maintain the existing plan, expedite the existing PO, or place the alternate order. An active recovery commitment may be accepted only once on day1. Repeated retries cannot create extra receipts, duplicate charges or a second recovery order. Missing the deadline leaves the delayed primary schedule in effect.

An illustrative tool contract:
- Read current inventory, orders, notices, resources and recovery offers.
- Commit a recovery choice; actual PO/budget/event state changes must follow.
- Release an integral production quantity for the current day, at most once; validate against available materials, remaining customer production requirement and daily capacity.
- Close the day and observe the next state.

Names and exact schemas will be designed after acceptance. Read calls do not advance time or consume budget. Invalid actions return a reason and leave operational state unchanged; their attempted execution remains auditable. Production may not consume unreceived components, exceed4/day or manufacture beyond the12 units needed for this fixture.

A production release is a binding scheduled operation, not an explanatory recommendation. It is reserved during the action phase and executed once at close. There is no unmodeled overtime or production on a different date.

## 5. Hand-worked expected consequences

These policies release the largest feasible quantity up to daily capacity and remaining order requirement. Shipments follow the same automatic rule for all policies.

| Policy | C receipts by day1–5 | P produced by day1–5 | P shipped by day1–5 | C remaining close day5 | Delivered on time |
|---|---|---|---|---:|---:|
| Maintain delayed primary PO | 0,0,0,8,0 | 4,0,0,4,4 | 0,0,4,4,4 | 0 | 4/12 |
| Expedite primary PO | 0,8,0,0,0 | 4,4,4,0,0 | 0,0,12,0,0 | 0 | 12/12 |
| Buy alternate supply | 0,8,0,8,0 | 4,4,4,0,0 | 0,0,12,0,0 | 8 | 12/12 |

| Policy | Undelivered at closes day3/day4/day5 | Incremental spend | Service penalties | Comparison cost |
|---|---|---:|---:|---:|
| Maintain delayed primary PO | 8 /4 /0 | USD0 | USD120 | USD120 |
| Expedite primary PO | 0 /0 /0 | USD24 | USD0 | USD24 |
| Buy alternate supply | 0 /0 /0 | USD40 | USD0 | USD40 |

These are arithmetic expectations, not measured simulator results. An independent implementation must verify them. The expedited outcome being cheapest in this one fixture does not establish a general optimal policy. The alternate policy is valid and should not fail feasibility grading merely because it costs more.

Useful intermediate checkpoints:
- All policies: close day1 has0 C and4 P, with no shipment yet.
- Expedite/alternate: close day2 has4 C and8 P; close day3 ships12 and leaves0 C/0 P.
- Maintain: close day3 ships4 and leaves8 undelivered; close day4 has4 C and4 undelivered.
- Alternate: day4 primary receipt remains real and leaves8 C, revealing the consequence of ordering extra supply.

## 6. Acceptance evidence

| Gate | Required proof |
|---|---|
| G1 Coherent initial world | Inspectable entities, commitments, rules, seed/calendar version and visibility definition |
| G2 Actual time progression | Log shows opening1 through close5, not a constant simulated_time field |
| G3 Executed disruption and recovery | Delay changes the primary event; expedite reschedules that PO; alternate creates a distinct PO while preserving the original |
| G4 Consequential state changes | Inventory, scheduled releases, completions, shipments, budget and penalties reconcile at each step |
| G5 Baseline differences | Run all three declared policies under the same initial world/event and match both tables above |
| G6 Independent checking | Check component/finished-goods conservation, order quantities, timing, capacity, budget and unique execution without trusting the simulator's own pass flag |
| G7 Failure behavior | Reject premature receipts, overproduction, production without material, over-budget/late recovery and duplicate commitments; no operational mutation on rejection |
| G8 Replay and data | Replaying the same recorded actions reproduces the state sequence and scorecard; produce one inspectable observable episode with private answers excluded |
| G9 Honest demonstration | Label scripted policies, assumptions, practitioner-review status and remaining limitations; screenshots complement traces and checks |

Required demonstration packet: event/action timeline, before/after state ledger, three-policy scorecard, checker results, replay command/log, one readable experience record and actual evidence screenshots when capture is available. Screenshot unavailability must be stated rather than replaced by a generated image.

Only after the user accepts this behavior and its assumptions should the detailed simulator specification and execution issues be finalized. Acceptance of this proposal would authorize that planning baseline, not claim the simulator is built.

Arithmetic and coverage checks for this proposal are recorded in [the validation file](dynamic-supplier-delay-v0.1-validation.json). They check the hand-worked expectations only; no simulator has been implemented or run for this proposal.

## 7. What comes afterward

Practitioner review tests the business assumptions. A real-LLM adapter and a small development evaluation follow a working, checked environment. A teacher-data pilot and fine-tuning experiment follow valid diverse scenarios. Static tasks may remain as auxiliary work; the60 existing static exports do not satisfy this gate.

Open for user review: whether this situation represents the intended first demonstration, whether the stated recovery/production/shipping rules are acceptable, and which assumptions need practitioner input. The five-day horizon, quantities and costs are proposals, not inherited user requirements.

