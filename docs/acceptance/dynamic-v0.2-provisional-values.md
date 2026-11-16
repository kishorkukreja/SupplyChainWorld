# S01 dynamic family v0.2: written rules and provisional-values table

Issue: [#36](https://github.com/kishorkukreja/SupplyChainWorld/issues/36) (REPAIR-17b). Parent: #17. Date: 2026-11-16.
Source of the repairs: [owner-practitioner review](../reviews/2026-11-16-practitioner-review-17.md), findings S1 to S7.

**Status: repair implemented and tested, awaiting practitioner re-review. Reviewed: no.** The reviewer is the project owner, so even a re-review is not independent.

**Every number below is PROVISIONAL, needs practitioner value.** The review confirmed or corrected no price, rate, weight, threshold or curve. The values were chosen by the assistant only so the mechanics can run and be hand-checked. They do not describe any real contract, supplier or customer. Nothing here is a model-ability claim.

The v0.1 scenario ([dynamic-supplier-delay-v0.1.md](dynamic-supplier-delay-v0.1.md)), its fixtures, tests and evidence are untouched. v0.2 sits beside it in new modules: `src/supplychainworld/{dynamic_v2,agent_runner_v2,dynamic_verifier_v2,dynamic_demo_v2}.py`, `fixtures/dynamic/v0.2/`, `scripts/run_dynamic_demo_v2.py`, `evidence/issue-36/`.

## 1. Rules as written (the basis for the hand-worked ledgers)

Day cycle, as in v0.1: opening (receipts, then signal, then firm notice), action phase, close.

1. **Opening.** Every unreceived lot whose arrival day equals today is received into component stock. Then a possible-delay signal is shown if today is the scenario's signal day. Then the firm notice is shown if today is its notice day.
2. **Firm notice.** A confirmed delay moves the arrival of the primary lot to the delayed day, unless the lot was already fully expedited (see 4). Otherwise the notice confirms the primary lot on time. Sudden scenarios have no signal and only the firm notice; warned scenarios have a signal first.
3. **Signal (S7).** It carries one probability-like hint (an integer percent) and fixed text. It never names the outcome, the revised date or the resolution day. A warned-and-delayed and a warned-and-no-delay scenario are observation-identical until the firm notice (test-enforced).
4. **Recovery commitments (S6).** Once any signal or notice is visible, the agent may commit `expedite` or `alternate` for a quantity of units, any number of times, on any day for which the rate card has a row, until the budget or availability runs out.
   - Unit cost and arrival day come from the rate card row for the commit day (rising cost on later days).
   - Expedite moves `quantity` units of the unreceived primary lot to the offered arrival day. It is refused if that arrival is not earlier than the lot's current arrival day (no benefit) or if `quantity` exceeds the lot's units. A partial expedite splits the lot; a whole-lot expedite retimes it.
   - Alternate buys `quantity` units as a new lot arriving on the offered day, up to a cumulative supplier availability.
   - Cost is `quantity x unit cost`, charged at commitment, against one shared recovery budget.
   - Each commitment executes once. A repeated commit id is refused; no second charge, no second lot. Not committing is the maintain policy.
5. **Production.** At most the daily capacity, at most the components on hand, and no more than open customer demand less finished stock on hand. One release per day, executed at close.
6. **Shipping and tier priority (S5).** At close, from each order's due day on, finished stock ships to open orders in descending tier weight, then order id, up to each order's remaining quantity.
7. **Penalty contract term (S2).** Per order, assessed at each close on or after the due day while units are undelivered (units still open after shipping):
   - `percent_of_value`: `floor(undelivered x unit value x rate / 100)` at every assessed close.
   - `fixed_per_unit`: `undelivered x rate`, once, at the due-day close only.
   - `per_unit_per_day`: `undelivered x rate` at every assessed close (the v0.1 rule).
8. **Backlog versus cancellation (S5).** A tier either backlogs (the order stays open to the horizon end, penalties continue) or cancels after a cancellation day: at that day's close, after shipping and penalty assessment, any remaining undelivered units are cancelled. A cancelled order accrues nothing further.
9. **Salvage (S3).** At the close of the last day, components on hand earn `rate x units`. Unreceived lots and finished goods earn nothing.
10. **Scorecard (S1, S4).** Five separate blocks, never combined into one number: `cost` (recovery spend, service penalties, salvage credit, net cost), `service` (OTIF orders met, on-time units, delivered, cancelled, unit-days late, per-order rows including days short), `tier_impact` (per tier rows and the priority-weighted unit-days late), `downstream` (cancelled units and value, units undelivered at end), `supply_risk` (ending components, pending inbound units, ending cover days, primary reliance percent, number of commitments, unused budget). Net cost is only a cost-block total; there is no overall score and no declared best policy.
    - OTIF per order: units delivered by the close of the due day equal the ordered quantity.
    - Unit-days late: the sum of undelivered units at each assessed close. Days short: number of assessed closes with a shortfall.
    - Priority-weighted unit-days late: the sum over orders of tier weight times unit-days late.
    - Cancelled order value: cancelled units times the order's unit value.
    - Primary reliance percent: `floor(100 x units from the primary supplier (original or expedited) / all inbound lot units)`.
    - Ending cover days: `floor(ending components / daily capacity)`.

These definitions of OTIF, lateness, downstream impact and supply risk are engineering proxies chosen so each reported dimension has a measurable counterpart. The practitioner has not confirmed them.

## 2. Provisional-values table

Marker: **PROVISIONAL, needs practitioner value** applies to every row.

### 2.1 Values shared by all four scenarios

| Value | Used | Marker | Reviewer open item it stands in for |
|---|---|---|---|
| Opening components | 4 | PROVISIONAL, needs practitioner value | none (carried from v0.1) |
| Daily production capacity | 4 units | PROVISIONAL, needs practitioner value | none (carried from v0.1) |
| Primary PO quantity | 8 units | PROVISIONAL, needs practitioner value | none (carried from v0.1) |
| Alternate supplier availability, cumulative | 8 units | PROVISIONAL, needs practitioner value | recovery cost curves |
| Recovery budget | USD 40 | PROVISIONAL, needs practitioner value | none (carried from v0.1) |
| Salvage per leftover component | USD 2 | PROVISIONAL, needs practitioner value | salvage rate |
| Tier weight, key | 3 | PROVISIONAL, needs practitioner value | tier definitions |
| Tier weight, standard | 1 | PROVISIONAL, needs practitioner value | tier definitions |
| Key tier shortfall rule | backlog, no cancellation | PROVISIONAL, needs practitioner value | tier definitions |
| Standard tier shortfall rule | cancel after day 5 (S4 only) | PROVISIONAL, needs practitioner value | tier definitions |
| Allocation priority | descending tier weight, then order id | PROVISIONAL, needs practitioner value | tier definitions |

### 2.2 Scenario values

| Scenario | Horizon | Class | Signal day / hint | Firm notice day | Outcome | Promised arrival | Delayed arrival |
|---|---|---|---|---|---|---|---|
| `s02-sudden-5d` | 5 | sudden | none | 1 | delay | 2 | 4 |
| `s02-warned-delayed-10d` | 10 | warned | day 1 / 60% | 2 | delay | 3 | 6 |
| `s02-warned-no-delay-10d` | 10 | warned | day 1 / 60% | 2 | none (confirmed on time) | 3 | not applicable |
| `s02-multitier-cancel-10d` | 10 | sudden | none | 1 | delay | 2 | 5 |

All values in this table are PROVISIONAL, needs practitioner value. The 60% hint is an authored number, not calibrated against any delay frequency. It is identical in the delayed and no-delay variants on purpose, so it carries no outcome information.

### 2.3 Recovery rate cards (cost curve by commit day, S6)

Each row is `day: unit cost USD, arrival day`. PROVISIONAL, needs practitioner value (this is the reviewer's "recovery cost curves for later days").

| Scenario | Expedite | Alternate |
|---|---|---|
| `s02-sudden-5d` | 1: 3, arr 2; 2: 4, arr 3 | 1: 5, arr 2; 2: 6, arr 3 |
| `s02-warned-delayed-10d` and `s02-warned-no-delay-10d` | 1: 3, arr 2; 2: 4, arr 3; 3: 5, arr 4 | 1: 5, arr 3; 2: 6, arr 4; 3: 7, arr 5 |
| `s02-multitier-cancel-10d` | 1: 3, arr 2; 2: 4, arr 3; 3: 5, arr 4 | 1: 5, arr 3; 2: 6, arr 4; 3: 7, arr 5 |

A whole-lot expedite on day 1 of the 5-day scenario costs 8 x 3 = USD 24 and a whole alternate lot 8 x 5 = USD 40, which reproduces the two v0.1 prices (also unconfirmed).

### 2.4 Customer orders and penalty contract terms (S2, S5)

| Scenario | Order | Tier | Quantity | Due day | Unit value USD | Penalty term | Rate |
|---|---|---|---|---|---|---|---|
| `s02-sudden-5d` | O1 | key | 12 | 3 | 10 | per unit per day | USD 10 |
| `s02-warned-delayed-10d` | O1 | key | 12 | 4 | 25 | percent of value, each assessed close | 10% |
| `s02-warned-no-delay-10d` | O1 | key | 12 | 4 | 25 | percent of value, each assessed close | 10% |
| `s02-multitier-cancel-10d` | K1 | key | 8 | 3 | 25 | fixed per unit, once at the due close | USD 6 |
| `s02-multitier-cancel-10d` | S1 | standard | 8 | 3 | 20 | percent of value, each assessed close | 10% |

All values PROVISIONAL, needs practitioner value. The three penalty term types are mechanisms the reviewer asked for ("percentage, fixed value per unit, depending on contract"); which type, rate, cap or grace period applies to which customer is the open item "penalty terms by contract".

### 2.5 Definitions that are also assumptions

| Definition | Marker |
|---|---|
| Penalty is assessed on units still undelivered at each close on or after the due day (carried from v0.1) | PROVISIONAL, needs practitioner value |
| A fixed-per-unit penalty is charged once at the due-day close | PROVISIONAL, needs practitioner value |
| Percent-of-value rounds down to a whole dollar per assessment | PROVISIONAL, needs practitioner value |
| Cancellation happens at the close of the tier's cancellation day, after penalty assessment, with no cancellation fee | PROVISIONAL, needs practitioner value |
| Salvage applies only to components on hand at the end of the horizon; none for finished goods or unreceived lots | PROVISIONAL, needs practitioner value |
| Expedite is refused when it would not make the lot arrive earlier | PROVISIONAL, needs practitioner value |
| The firm notice does not move a fully expedited primary lot | PROVISIONAL, needs practitioner value |
| Metric proxies for OTIF, lateness, downstream impact and supply risk (section 1, item 10) | PROVISIONAL, needs practitioner value |

## 3. What to confirm at re-review

1. Salvage rate (and whether finished goods or unreceived lots earn any).
2. Penalty terms per contract: type, rate, cap, grace period, and whether percent-of-value is daily or one-time.
3. Tier definitions, weights, which tiers backlog and which cancel and after how many days, and any cancellation fee.
4. Recovery price and lead-time curves by day, minimum order sizes, and alternate supplier capacity.
5. Whether the proxies for OTIF, downstream impact and supply risk match what the reviewer meant by those four dimensions.
6. Whether the warned-signal hint should be a stated percent at all, and typical warned-versus-sudden frequencies.

## 4. Implemented, tested, practitioner-reviewed

- Implemented: yes. Findings S1 to S7 each have a mechanism in `dynamic_v2.py` (see section 1) behind the existing tool names in `agent_runner_v2.py`.
- Tested: yes. Hand-worked ledgers for 20 episodes (4 scenarios x 5 declared policies), an independent verifier with adversarial tests, replay of every episode and a leak scan. Details in `evidence/issue-36/`.
- Practitioner-reviewed: **no.** The repair awaits re-review. No value is confirmed.
