# Supplier allocation v1.0

This public synthetic family implements spec sections 3 and 7 for one receiving facility, one planning period, integral component units, Gregorian ISO dates and USD. It excludes taxes, FX, tiers, live orders, negotiation, multi-period scheduling and browser use. Quotes explicitly encode qualification. These are pilot conventions requiring practitioner review, not universal purchasing practice.

Net requirement per item is max(0, demand minus usable stock minus committed inbound arriving on or before the item deadline). Held/reserved stock and late inbound do not count. Every item must receive net requirement through net requirement plus its explicit excess allowance. MOQ does not authorize excess. A positive quote award must meet MOQ, be divisible by its order multiple, and not exceed capacity. Qualification, quote validity on as_of (inclusive), and arrival by due_date (inclusive) are mandatory. Quantities are nonnegative integers; duplicate supplier-item rows and unknown identifiers are invalid. Missing allocated item coverage is a shortage; omitted zero rows are allowed. Supplier-item quote keys are unique.

Use exact Decimal arithmetic. For each selected supplier, add quantity times (unit price plus variable freight) across its items, add the supplier fixed charge exactly once, then round that supplier's subtotal to USD cents using ROUND_HALF_UP. Total landed cost is the sum of those rounded supplier subtotals. No separate per-unit rounding occurs. Budget is inclusive and hard. All money and ratios are decimal strings in JSON. Missing price or freight requires clarification; never substitute zero. The quote's fixed charge convention applies once per selected supplier per episode, regardless of item count.

Concentration means each supplier's rounded landed spend (including fixed charge) divided by total landed spend, across all items. Compare by exact multiplication against the supplied decimal limit; never sum unlike item quantities. For zero total spend the concentration check passes. A null limit means no cap. This convention can make inexpensive suppliers harder to balance; it is deliberate and needs practitioner review.

Awards establish feasibility separately from economic quality. Minimize total landed cost among feasible awards; every exact-cost tie is valid. Pilot reference tasks report objective gap and use zero monetary tolerance. A feasible suboptimal award remains feasible and must be labeled suboptimal rather than a hard-policy violation. When optimum is zero, report absolute gap and omit percentage gap.

A missing required commercial term produces a clarification request naming its field and visible evidence. The missing-term reference's response policy is record_and_escalate: record the request and escalate without inventing a response. Operational infeasibility requires a supported constraint argument; solver timeout is insufficient. Exception evidence is a list of visible-record observations. The checker should independently verify the stated exception against visible inputs, not require exact text equality.

The agreed world schema is represented by each fixture's `world`; awards use `kind`, `allocations` with supplier/item/quantity, `claimed_total_cost`, and `evidence`. Exception submissions use `kind`, `evidence`, and an optional `field`. Schema version is 1.0. `expected`, `known_wrong`, and `review` are public example answer material and must be excluded from agent observations. These public examples are never sealed evaluation data.

| Case | Diagnostic | Independent calculation |
| --- | --- | --- |
| ref-01 | Inventory and timely inbound | Net 7−2−1=4, cost 8 |
| ref-02 | Fixed freight tradeoff | Supplier A 4+5=9; B 8 |
| ref-03 | MOQ and multiple | A4+B1 costs 6 |
| ref-04 | Arrival deadline | Cheap A late; B4 costs 8 |
| ref-05 | Qualification and ties | B/C splits cost 8 |
| ref-06 | Spend concentration | Equal 2/2 split costs 4 |
| ref-07 | Binding budget and decimal precision | 4×(1.005+.005)=4.04 |
| ref-08 | Explicit excess permission | Buy 4 for demand 3 costs 4 |
| ref-09 | Missing freight | Request missing field and escalate |
| ref-10 | Capacity infeasibility | Eligible 2+1 < demand 4 |

Each JSON carries a source label, a hand calculation, expected submission, known wrong submission with defect, and review status. `tests/test_reference_cases.py` independently enumerates all quote quantities for these tiny instances and rejects known wrong awards without using production solver/checker logic. Arithmetic verification is complete only when its command passes. All ten cases still require practitioner signoff for policy conventions and business realism; no such signoff has been obtained.
