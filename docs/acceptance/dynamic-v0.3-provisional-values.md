# S01 dynamic family v0.3: written rules and provisional-values table

Issue: [#36](https://github.com/kishorkukreja/SupplyChainWorld/issues/36). Parent: #17. Date: 2026-11-17.
Source of the changes: [owner-practitioner re-review, round 2](../reviews/2026-11-17-practitioner-re-review-17.md), section "Dynamic scenario S01 v0.2". Previous version: [dynamic-v0.2-provisional-values.md](dynamic-v0.2-provisional-values.md), which is left as it was.

**Status: implemented and tested, awaiting practitioner re-review. Reviewed: no. Not independent** (the reviewer is the project owner).

**Every number below is PROVISIONAL, needs practitioner value.** The reviewer gave ranges or direction, never a confirmed figure. Where a range was given, a point inside it was chosen only so the mechanics can run and be hand-checked. Nothing here describes a real contract, supplier or customer, and nothing here is a model-ability claim.

v0.3 sits beside v0.1 and v0.2 in new modules: `src/supplychainworld/{dynamic_v3,agent_runner_v3,dynamic_verifier_v3,dynamic_demo_v3}.py`, `fixtures/dynamic/v0.3/{scenarios,hand-ledgers}.json`, `scripts/{run_dynamic_demo_v3,generate_hand_ledgers_v03}.py`, `evidence/issue-36-v03/`. No v0.1 or v0.2 file was edited.

## 1. Rules as written (the basis for the hand-worked ledgers)

The day cycle (opening, action, close), production, shipping order, the five scorecard blocks and the metric proxies are as in v0.2 section 1 (the reviewer accepted the proxies as written, so their definitions are unchanged). What changed:

1. **Expedite (re-review: 30 to 50% premium on normal unit cost).** The scenario states a base primary unit cost (provisional USD 10 per component). An expedite row gives a premium percent and an arrival day for a commit day. Unit cost is `base x premium / 100`, charged on each unit moved earlier. The base price is not charged again because the primary PO is paid anyway. Day-1 premium is 40%, so USD 4 a unit.
2. **Alternate supplier (re-review: 20 to 40% premium over the primary unit cost).** An alternate row gives a premium percent and an arrival day. Unit cost is `base + base x premium / 100`, charged on every unit of the new lot, so USD 13 a unit at the 30% day-1 premium. The primary lot still arrives and is still paid; the alternate units are extra stock. Cumulative alternate availability is capped as in v0.2 (8 units).
3. **Rate cards rise by day.** Later commit days carry a higher premium (a provisional day multiplier on the day-1 premium, shown in section 2.3) and an arrival day that follows the commit day.
4. **Whole dollars.** Quantities and money are whole numbers, so `base x premium` must be a multiple of 100 for every rate card cell. The scenario validator rejects a cell that would give a fractional dollar.
5. **Late penalty (re-review: 1 to 2% of order value per day late, capped).** Per order, assessed at each close on or after the due day while units are undelivered:
   - `percent_of_value`: `floor(undelivered x unit value x rate_bp / 10000)` at every assessed close. The rate is in basis points (150 = 1.5% per day).
   - `fixed_per_unit` and `per_unit_per_day`: unchanged from v0.2 (`undelivered x rate`, once at the due-day close, or at every assessed close).
   - **Total cap, any term:** the order's cumulative penalty never exceeds `floor(order quantity x unit value x cap_pct / 100)`. Each assessment is `max(0, min(amount, cap - already charged))`. Lateness (unit-days late, days short) is still recorded after the cap is reached.
6. **Salvage by part class (re-review: "depends on part").** Each scenario declares `part_class` (standard or custom). A leftover component at the close of the last day earns `floor(base unit cost x class fraction / 100)`: standard 60%, custom 0%. The fraction applies to the base primary unit cost whichever supplier delivered the unit.
7. **Cancellation (re-review: 5 to 7 days after the due date).** A cancel-after tier cancels any units of an order still undelivered at the close of day `due day + N`, after shipping and penalty assessment (N = 6). A backlog tier (key) never cancels. A cancelled order accrues nothing further.
8. **Tier weights** are 5 (key) and 1 (standard). Shipping priority and the priority-weighted lateness metric use these weights.
9. **Warned-signal hint (re-review: qualitative).** The signal carries only a `level` (low, medium or high) and a fixed text. It carries no percent, no outcome, no revised date. The level is declared by the scenario and is identical in the delayed and no-delay warned variants; the observation streams are identical until the firm notice (test-enforced), and the verifier's leak scan rejects any other level, any numeric hint and any outcome wording.

## 2. Provisional-values table

Marker: **PROVISIONAL, needs practitioner value** applies to every row. "Changed from v0.2" says what moved and why.

### 2.1 Values shared by all five scenarios

| Value | v0.3 | Changed from v0.2 | Reviewer input it reflects | Marker |
|---|---|---|---|---|
| Base primary unit cost | USD 10 per component | new (v0.2 had flat unit costs only) | stated base for percent premiums | PROVISIONAL, needs practitioner value |
| Expedite premium, day 1 | 40% (USD 4 a unit) | was USD 3 a unit flat | range 30 to 50%, 40 chosen | PROVISIONAL, needs practitioner value |
| Alternate premium, day 1 | 30% (USD 13 a unit for the whole new lot) | was USD 5 a unit | range 20 to 40%, 30 chosen | PROVISIONAL, needs practitioner value |
| Late penalty rate | 1.5% of undelivered value per day (150 bp) | was 10% per assessed close | range 1 to 2% per day, 1.5 chosen | PROVISIONAL, needs practitioner value |
| Penalty total cap | 10% of order value | new | reviewer did not confirm a cap value; the 5 to 10% in the question text is not a confirmed answer | PROVISIONAL, needs practitioner value |
| Salvage fraction, standard part | 60% of base cost (USD 6) | was USD 2 flat | "depends on part" | PROVISIONAL, needs practitioner value |
| Salvage fraction, custom part | 0% (USD 0) | new | "depends on part" | PROVISIONAL, needs practitioner value |
| Standard-tier cancellation | 6 days after each order's due day | was day 5 of the horizon | range 5 to 7 days, 6 chosen | PROVISIONAL, needs practitioner value |
| Key-tier shortfall rule | backlog, no cancellation | unchanged | "key tier keeps backlog" | PROVISIONAL, needs practitioner value |
| Tier weight, key | 5 | was 3 | 5 to 1 | PROVISIONAL, needs practitioner value |
| Tier weight, standard | 1 | unchanged | 5 to 1 | PROVISIONAL, needs practitioner value |
| Warned-signal hint | qualitative level, `medium` | was an integer percent (60) | qualitative low, medium, high | PROVISIONAL, needs practitioner value |
| Recovery budget | USD 120 | was USD 40 | none; raised because a whole alternate lot now costs USD 104 | PROVISIONAL, needs practitioner value |
| Finished-good unit value (order value basis) | USD 100 (USD 80 for the standard order S1) | was USD 10 to 25 | none; chosen so a 1.5% a day penalty is a visible number | PROVISIONAL, needs practitioner value |
| Opening components, daily capacity, primary PO quantity, alternate availability | 4, 4 units, 8 units, 8 units | unchanged | none | PROVISIONAL, needs practitioner value |
| Allocation priority | descending tier weight, then order id | unchanged | none | PROVISIONAL, needs practitioner value |

### 2.2 Scenario values

| Scenario | Horizon | Class | Part | Signal day / level | Firm notice day | Outcome | Promised arrival | Delayed arrival | Changed from v0.2 |
|---|---|---|---|---|---|---|---|---|---|
| `s03-sudden-5d` | 5 | sudden | standard | none | 1 | delay | 2 | 4 | re-based from `s02-sudden-5d` |
| `s03-warned-delayed-10d` | 10 | warned | custom | day 1 / medium | 2 | delay | 3 | 6 | level replaces 60%; part class declared |
| `s03-warned-no-delay-10d` | 10 | warned | custom | day 1 / medium | 2 | none (confirmed on time) | 3 | not applicable | level replaces 60%; identical to the delayed twin except the outcome |
| `s03-multitier-cancel-10d` | 10 | sudden | standard | none | 1 | delay | 2 | 5 | cancellation lag, weights, values re-based |
| `s03-alt-cheaper-10d` | 10 | sudden | standard | none | 1 | delay | 2 | 9 | **new**: long delay and a slow expedite lane (section 2.3) |

### 2.3 Rate cards (cost curve by commit day)

Each row is `day: premium %, arrival day`. Unit cost: expedite `10 x premium / 100`, alternate `10 + 10 x premium / 100`. The multiplier is the row premium over the day-1 premium. PROVISIONAL, needs practitioner value. Day 2 and 3 premiums above the reviewer's range are the "day multipliers" the rate card needs; the reviewer gave no figure for them.

| Scenario | Expedite | Alternate | Changed from v0.2 |
|---|---|---|---|
| `s03-sudden-5d` | 1: 40% (USD 4), arr 2; 2: 50% (USD 5, x1.25), arr 3 | 1: 30% (USD 13), arr 2; 2: 40% (USD 14, x1.33), arr 3 | v0.2 flat USD 3 and 4 / USD 5 and 6; arrival days unchanged |
| `s03-warned-delayed-10d`, `s03-warned-no-delay-10d`, `s03-multitier-cancel-10d` | 1: 40% (USD 4), arr 2; 2: 50% (USD 5), arr 3; 3: 60% (USD 6, x1.5), arr 4 | 1: 30% (USD 13), arr 3; 2: 40% (USD 14), arr 4; 3: 50% (USD 15, x1.67), arr 5 | v0.2 flat USD 3 to 5 / USD 5 to 7; arrival days unchanged |
| `s03-alt-cheaper-10d` | 1: 40% (USD 4), arr **8**; 2: 50% (USD 5), arr **8** | 1: 30% (USD 13), arr 3; 2: 40% (USD 14), arr 4 | new. Authored so expedite is a slow lane (seven days of lead time, one day better than the delayed arrival of day 9) while a spot buy lands on day 3. These lead times are not reviewer values. |

**Cost relationship, changed from v0.2.** v0.2 priced alternate at about 1.7x expedite per unit (5 versus 3). On the v0.3 numbers alternate costs USD 13 a unit against USD 4 for expedite on day 1 (about 3.3x), because the alternate unit price includes the base price and the primary lot is still paid. Compared as premiums only (30% versus 40%) alternate is the cheaper premium; see open item 1.

### 2.4 Customer orders and penalty contract terms

| Scenario | Order | Tier | Quantity | Due day | Unit value USD | Penalty term | Rate | Cap | Changed from v0.2 |
|---|---|---|---|---|---|---|---|---|---|
| `s03-sudden-5d` | O1 | key | 12 | 3 | 100 | percent of value, each assessed close | 1.5% (150 bp) | 10% of order value (USD 120) | was USD 10 per unit per day, uncapped |
| `s03-warned-delayed-10d` and `-no-delay-10d` | O1 | key | 12 | 4 | 100 | percent of value, each assessed close | 1.5% | 10% (USD 120) | was 10% per close on USD 25 |
| `s03-multitier-cancel-10d` | K1 | key | 8 | 3 | 100 | fixed per unit, once at the due close | USD 6 | 10% (USD 80) | cap added |
| `s03-multitier-cancel-10d` | S1 | standard | 8 | 3 | 80 | percent of value, each assessed close | 1.5% (rounds down, 8 x 80 x 1.5% = 9.6 charged as 9) | 10% (USD 64) | was 10% per close on USD 20; cancels at due + 6 = day 9 |
| `s03-alt-cheaper-10d` | O1 | key | 12 | 3 | 100 | percent of value, each assessed close | 1.5% | 10% (USD 120) | new |

All values PROVISIONAL, needs practitioner value. The three penalty term types remain available as contract terms; fixed per unit appears in one fixture (K1) and per unit per day is exercised by unit tests. Percent of value is charged on the undelivered part of the order (v0.2 behavior), not on the whole order value; see open item 5.

### 2.5 Definitions that are also assumptions

| Definition | Changed from v0.2 | Marker |
|---|---|---|
| Penalty is assessed on units still undelivered at each close on or after the due day | unchanged | PROVISIONAL, needs practitioner value |
| Percent-of-value rounds down to a whole dollar per assessment, then the cap is applied | cap is new | PROVISIONAL, needs practitioner value |
| The cap applies to the cumulative penalty of an order, whatever the term | new | PROVISIONAL, needs practitioner value |
| Cancellation is at the close of due day + N, after penalty assessment, with no fee | N replaces a horizon day | PROVISIONAL, needs practitioner value |
| Salvage is a class fraction of the base primary unit cost, for components on hand at the end only | class fractions new | PROVISIONAL, needs practitioner value |
| Alternate buy is charged in full and the primary lot still arrives | price basis new | PROVISIONAL, needs practitioner value |
| Expedite premium is charged only on units moved earlier | price basis new | PROVISIONAL, needs practitioner value |
| Expedite is refused when it would not make the lot arrive earlier; the firm notice does not move a fully expedited lot | unchanged | PROVISIONAL, needs practitioner value |
| Metric proxies for OTIF, lateness, downstream impact and supply risk | unchanged, accepted by the reviewer as written | accepted as written; the values stay PROVISIONAL |

## 3. Open items for the reviewer

1. **Alternate versus expedite cost basis.** The re-review notes alternate "can be cheaper than expedite". That holds only when the alternate premium (USD 3 a unit) is compared with the expedite premium (USD 4). This build prices the alternate unit at USD 13 because the primary lot still arrives and is still paid. If the intended reading is that an alternate buy replaces primary units (so only the premium is incremental), say so and the price basis changes.
2. Penalty cap value (10% used, not confirmed) and whether the cap is per order or per contract.
3. Salvage fraction by part class (60 and 0 used) and whether it applies to alternate-supplier units at their own price.
4. Qualitative hint wording (level only is shown) and which level a scenario should carry.
5. Percent of value on the undelivered part (used) or on the whole order value while any unit is late.
6. Finished-good unit value relative to component cost (10 to 1 used). With a 1.5% a day penalty capped at 10%, the penalty is small beside the recovery premiums, so recovery does not pay back on net cost in most scenarios; this is a finding of the chosen ratio, not a validated result.
7. Day multipliers for later commit days, and the lead times in the slow-expedite scenario.

## 4. Implemented, tested, practitioner-reviewed

- Implemented: yes. Each re-review change has a mechanism in `dynamic_v3.py` and the independent `dynamic_verifier_v3.py`.
- Tested: yes. Hand-worked ledgers for 25 episodes (5 scenarios x 5 declared policies) regenerated by `scripts/generate_hand_ledgers_v03.py` (it imports no project code), an independent verifier with adversarial tests, replay of every episode, a leak scan of every episode, and a paired-observation test for the warned variants. Details in `evidence/issue-36-v03/`.
- Practitioner-reviewed: **no.** Not independent. No value is confirmed.
