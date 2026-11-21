# S01 dynamic family v0.4: written rules and provisional-values table

Issue: [#36](https://github.com/kishorkukreja/SupplyChainWorld/issues/36). Parent: #17. Date: 2026-11-21.
Source of the changes: owner-practitioner re-review, round 3 (reviewer decisions relayed to the implementer; the earlier review notes are in [the round 2 review](../reviews/2026-11-17-practitioner-re-review-17.md)). Previous version: [dynamic-v0.3-provisional-values.md](dynamic-v0.3-provisional-values.md), which is left as it was.

**Status: implemented and tested, awaiting practitioner re-review. Reviewed: no. Not independent** (the reviewer is the project owner).

**Every number below is PROVISIONAL, needs practitioner value.** Nothing here describes a real contract, supplier or customer, and nothing here is a model-ability claim.

v0.4 sits beside v0.1, v0.2 and v0.3 in new modules: `src/supplychainworld/{dynamic_v4,agent_runner_v4,dynamic_verifier_v4,dynamic_demo_v4}.py`, `fixtures/dynamic/v0.4/{scenarios,hand-ledgers}.json`, `scripts/{run_dynamic_demo_v4,generate_hand_ledgers_v04}.py`, `evidence/issue-36-v04/`. No v0.1, v0.2 or v0.3 file, static file, fixture, test or evidence was edited. The v0.3 scenario validator, world machinery, runner and scripted policies are reused by import.

## UNRESOLVED ASSUMPTION for the reviewer (read this first)

The reviewer chose **compare premiums only** for the alternate supplier. That leaves a modelling question the reviewer has not answered:

> If only the premium is charged for an alternate buy, what is the base cost of the alternate units, and what happens to the primary lot's surplus?

v0.4 implements the simplest explicit convention so the mechanics can run. **It is an assumption, not a reviewer value, and it needs the reviewer's answer:**

1. **Base purchase cost is cost-neutral.** The base purchase cost of any recovery lot (expedited units and alternate units alike) is identical across policies and is excluded from the comparison, as the primary PO cost was excluded in v0.1. Only the premium is incremental.
2. **Alternate-bought surplus earns no salvage.** Components left on hand at the horizon end are presumed to be alternate-bought first. The salvage-eligible count is `ending components - min(ending components, alternate units received)`, and only those earn the class salvage credit. A premium-only reading therefore cannot create a salvage windfall. A test proves a policy cannot profit from buying surplus (even with salvage set to 100% of the base cost).
3. **The primary lot still arrives and its own surplus is still credited** at the class rate (nothing in the scripted fixtures leaves primary surplus, so the fixtures show USD 0 salvage everywhere; the unit tests show the primary-surplus case).

Open alternatives the reviewer may prefer: the alternate lot replaces primary units (so the primary lot shrinks or is cancelled), or the alternate base cost is charged at its own price and surplus earns salvage. Either changes the headline numbers.

## 1. Rules as written (the basis for the hand-worked ledgers)

Everything in [v0.3 section 1](dynamic-v0.3-provisional-values.md) applies except the items below. Day cycle, production, shipping order, the five scorecard blocks, metric proxies, signal level, tier weights and the cancellation lag are carried forward.

1. **Expedite (carried forward).** Premium on the base unit cost, charged per unit moved earlier: `base x premium / 100`. Day 1 premium 40%, USD 4 a unit.
2. **Alternate supplier (changed).** Incremental cost is the premium only: `base x premium / 100` per unit of the new lot, USD 3 a unit at the 30% day-1 premium (v0.3 charged `base + premium`, USD 13). It is now directly comparable with the expedite premium, and is the cheaper premium on every commit day. Cumulative availability is capped at 8 units as before. The primary lot still arrives.
3. **Late penalty cap (changed).** The cap is 20% of order value (was 10%). The percent penalty stays 1.5% a day (150 bp) on the undelivered part of the order. Fixed per unit and per unit per day terms are unchanged.
4. **Salvage (changed for alternate-bought surplus only).** Standard part 60% of the base cost, custom 0%, as before, for components on hand at the end, except the no-salvage convention in the section above.
5. **Recovery budget (changed, see table).** USD 40.
6. **Rate cards, cancellation, weights, hint.** Unchanged.

## 2. Provisional-values table

Marker: **PROVISIONAL, needs practitioner value** applies to every row.

### 2.1 Values shared by all five scenarios

| Value | v0.4 | Changed from v0.3 | Reviewer input it reflects | Marker |
|---|---|---|---|---|
| Alternate unit cost basis | premium only, USD 3 a unit on day 1 (30% of USD 10) | **changed**: was base plus premium, USD 13 a unit | "compare premiums only" | PROVISIONAL, needs practitioner value |
| Base cost of a recovery lot | cost-neutral, excluded from every policy | **new**, UNRESOLVED ASSUMPTION | none; reviewer has not answered | PROVISIONAL, needs practitioner value |
| Salvage on alternate-bought surplus | none | **new**, UNRESOLVED ASSUMPTION | none | PROVISIONAL, needs practitioner value |
| Base primary unit cost | USD 10 per component | unchanged | stated base for percent premiums | PROVISIONAL, needs practitioner value |
| Expedite premium, day 1 | 40% (USD 4 a unit) | unchanged | range 30 to 50% | PROVISIONAL, needs practitioner value |
| Later-day premiums | expedite 50% and 60%, alternate 40% and 50% | unchanged | above the 30 to 50% range, accepted | PROVISIONAL, needs practitioner value |
| Late penalty rate | 1.5% of undelivered value per day (150 bp) | unchanged | accepted | PROVISIONAL, needs practitioner value |
| Penalty total cap | **20%** of order value | **changed** from 10% | reviewer chose 20% | PROVISIONAL, needs practitioner value |
| Salvage fraction, standard part | 60% of base cost (USD 6), components on hand at the end | unchanged (but see alternate surplus) | accepted | PROVISIONAL, needs practitioner value |
| Salvage fraction, custom part | 0% | unchanged | accepted | PROVISIONAL, needs practitioner value |
| Standard-tier cancellation | 6 days after each order's due day | unchanged | accepted | PROVISIONAL, needs practitioner value |
| Key-tier shortfall rule | backlog, no cancellation | unchanged | accepted | PROVISIONAL, needs practitioner value |
| Tier weights | key 5, standard 1 | unchanged | accepted | PROVISIONAL, needs practitioner value |
| Warned-signal hint | qualitative level, `medium` | unchanged | accepted | PROVISIONAL, needs practitioner value |
| Recovery budget | **USD 40** | **changed** from USD 120. The v0.3 reason for USD 120 (a whole alternate lot cost USD 104) no longer holds. USD 40 keeps the budget binding for a full expedite (USD 32) plus a full alternate buy (USD 24). The reviewer gave no figure | none | PROVISIONAL, needs practitioner value |
| Finished-good unit value | USD 100 (USD 80 for standard order S1) | unchanged | none | PROVISIONAL, needs practitioner value |
| Opening components, daily capacity, primary PO quantity, alternate availability | 4, 4 units, 8 units, 8 units | unchanged | none | PROVISIONAL, needs practitioner value |
| Metric proxies | OTIF, lateness, downstream impact, supply risk | unchanged | accepted as written | accepted as written; values stay PROVISIONAL |

### 2.2 Scenario values

Scenario ids are renamed `s04-*`; the mechanics are the same as the `s03-*` twins. Horizon, class, part, signal, notice day, outcome, promised and delayed arrival days are unchanged from v0.3.

| Scenario | Horizon | Class | Part | Signal day / level | Notice day | Outcome | Promised / delayed arrival | Changed from v0.3 |
|---|---|---|---|---|---|---|---|---|
| `s04-sudden-5d` | 5 | sudden | standard | none | 1 | delay | 2 / 4 | cap 20%, budget 40, alternate price basis |
| `s04-warned-delayed-10d` | 10 | warned | custom | day 1 / medium | 2 | delay | 3 / 6 | same |
| `s04-warned-no-delay-10d` | 10 | warned | custom | day 1 / medium | 2 | none | 3 / n.a. | same |
| `s04-multitier-cancel-10d` | 10 | sudden | standard | none | 1 | delay | 2 / 5 | same |
| `s04-alt-cheaper-10d` | 10 | sudden | standard | none | 1 | delay | 2 / 9 | same (the authored slow-lane scenario is kept, accepted) |

### 2.3 Rate cards (cost curve by commit day)

Each row is `day: premium %, arrival day`. Unit cost is `10 x premium / 100` for both suppliers.

| Scenario | Expedite | Alternate | Changed from v0.3 |
|---|---|---|---|
| `s04-sudden-5d` | 1: 40% (USD 4), arr 2; 2: 50% (USD 5), arr 3 | 1: 30% (USD 3), arr 2; 2: 40% (USD 4), arr 3 | alternate unit cost USD 13 and 14 become USD 3 and 4 |
| `s04-warned-delayed-10d`, `s04-warned-no-delay-10d`, `s04-multitier-cancel-10d` | 1: 40% (USD 4), arr 2; 2: 50% (USD 5), arr 3; 3: 60% (USD 6), arr 4 | 1: 30% (USD 3), arr 3; 2: 40% (USD 4), arr 4; 3: 50% (USD 5), arr 5 | alternate USD 13, 14, 15 become USD 3, 4, 5 |
| `s04-alt-cheaper-10d` | 1: 40% (USD 4), arr 8; 2: 50% (USD 5), arr 8 | 1: 30% (USD 3), arr 3; 2: 40% (USD 4), arr 4 | alternate USD 13 and 14 become USD 3 and 4 |

On every commit day the alternate premium (USD 3, 4, 5) is below the expedite premium (USD 4, 5, 6).

### 2.4 Customer orders and penalty contract terms

| Scenario | Order | Tier | Quantity | Due day | Unit value USD | Penalty term | Rate | Cap | Changed from v0.3 |
|---|---|---|---|---|---|---|---|---|---|
| `s04-sudden-5d` | O1 | key | 12 | 3 | 100 | percent of value, each assessed close | 1.5% (150 bp) | 20% of order value (USD 240) | cap 10% to 20% |
| `s04-warned-*` (two scenarios) | O1 | key | 12 | 4 | 100 | percent of value | 1.5% | 20% (USD 240) | cap |
| `s04-multitier-cancel-10d` | K1 | key | 8 | 3 | 100 | fixed per unit, once at the due close | USD 6 | 20% (USD 160) | cap |
| `s04-multitier-cancel-10d` | S1 | standard | 8 | 3 | 80 | percent of value, rounds down | 1.5% | 20% (USD 128) | cap; cancels at due + 6 = day 9 |
| `s04-alt-cheaper-10d` | O1 | key | 12 | 3 | 100 | percent of value | 1.5% | 20% (USD 240) | cap |

Percent of value stays on the undelivered part (accepted). In every scripted episode the largest cumulative penalty on one order is USD 78 (slow-lane scenario, maintain), so the raised cap never binds there; it matters only in tests that shorten the cap or lengthen the delay.

## 3. Open items for the reviewer

1. **The unresolved assumption above** (base cost of recovery lots, alternate surplus and the primary lot's surplus). This is the item the reviewer must answer.
2. Recovery budget (USD 40 chosen only to keep the budget binding).
3. Whether the cap is per order (used) or per contract.
4. Day multipliers for later commit days and the slow-lane lead times (carried forward, accepted).
5. Finished-good unit value relative to component cost (10 to 1 used). With a 1.5% a day penalty capped at 20% the penalty is still small beside the premiums in the short-delay scenarios.

## 4. Implemented, tested, practitioner-reviewed

- Implemented: yes. Each round 3 decision has a mechanism in `dynamic_v4.py` and the independent `dynamic_verifier_v4.py`.
- Tested: yes. Fresh hand-worked ledgers for 25 episodes (5 scenarios x 5 declared policies) regenerated by `scripts/generate_hand_ledgers_v04.py` (it imports no project code) and checked against the committed JSON by a test; an independent verifier with an AST test and sabotage tests; replay and leak scan of every episode; a test that a policy cannot profit from buying surplus. Details in `evidence/issue-36-v04/`.
- Practitioner-reviewed: **no.** Not independent. No value is confirmed.
