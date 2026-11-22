# S01.3 assessment: can an agent assess production and delivery exposure from what the tools show?

Plain-language verdict first, then the method and the evidence. All numbers in the scenarios are PROVISIONAL,
needs practitioner value. This note is about the software observations only. No language model was run, so it says
nothing about whether any model can do the assessment. It claims no practitioner review.

## Verdict

| Version | Can the quantities be computed from the observations alone? | Verdict |
|---|---|---|
| v0.1 | Not exactly. The size of the incoming supplier order (8 components in the fixtures) is never shown. Two worlds that differ only in that number look identical until the delivery arrives, then have different results. | **Insufficient (finding F5).** Recommendation: use v0.2 to v0.4 for any S01.3 claim. v0.1 stays as it is. |
| v0.2, v0.3, v0.4 | Yes for the quantities: units at risk, earliest feasible delivery day, shortfall under each recovery option, penalties and spend. Computed from the view alone they equal the independent verifier's ground truth on generated scenarios and on every committed fixture, every day, every option. | **Quantities sufficient.** |
| v0.2, v0.3, v0.4 | Not for the rules that turn those quantities into outcomes. Nothing in an observation says that goods arriving on a day can be used that day, that shipping only starts on the due day, in what order several due orders are served, or what a percent penalty rate means (whole percent in v0.2, basis points in v0.3 and v0.4). A wrong guess changes the answer (witness tests). | **Partial (finding F6).** Recommendation below. |
| v0.2, v0.3, v0.4 before the firm notice | Only a range. While a delay is merely warned the visible plan is the promise, so the assessment is a lower bound; "the primary order never arrives" is the upper bound. The truth lies between, and the warned and no-delay twins are indistinguishable (by design). | **Bounds only, correct by design (finding F7).** |

So the scenario map's caution stands: a scripted baseline does not prove S01.3, and neither does this test. What the
test shows is narrower and useful: for v0.2 to v0.4 the tool observations contain every number an assessor needs.
Whether a model can do the assessment, and whether the unstated rules are guessed correctly, are separate questions
that need a model run and the recommended fix.

## Method

* The assessor (`tests/support/s01_assess.py`) receives only `clock`, `state`, `rules` and `tools` of one agent view.
  Test `agent_only(view)` strips everything else. It uses no scenario object, no simulator internals and no verifier output.
* From a view at the opening of any day it projects the rest of the horizon under one of three options: keep the
  current plan (`maintain`), expedite as many units as today's offer and the remaining budget allow
  (`expedite_max`), or buy the largest affordable alternate lot (`alternate_max`). It reports units at risk
  (units not delivered by the close of the order's due day, per order and in total), the earliest feasible delivery
  day (first day every wanted unit is delivered), the penalties, and the recovery spend.
* Ground truth: the same episode is executed through the real runner with that option taken on that day and greedy
  production, then re-derived by the independent verifier from the commands (`report.scorecard`, `report.ledger`).
  The verifier must report no violation. The simulator's own numbers are never used as the answer.
* Comparison rule: if the firm notice is visible (or the disruption turns out not to happen) the assessment must
  equal the truth exactly. If a delay is only warned the assessment must not exceed the truth and the worst case
  must not fall below it.
* Property tests (Hypothesis, ci profile) draw scenario parameters, a decision day and an option. Another test runs
  every committed fixture x every day x every option. A coverage check asserts that exact and bounded comparisons
  were really made for every option in every version.

## Evidence (test names)

* `tests/test_s01_assessment_property.py`
  * `Assessment_v02`, `Assessment_v03`, `Assessment_v04`:
    `test_assessment_from_observations_matches_the_verifier_on_generated_scenarios`,
    `test_every_fixture_every_decision_day_every_option`,
    `test_zz_the_generated_runs_made_exact_and_bounded_comparisons_for_every_option`,
    `test_the_firm_notice_changes_what_the_agent_sees_but_the_warning_does_not`.
  * `V01ObservationsAreInsufficient`: the twin-scenario property, a witness that the twins differ in outcome, and a
    check that no observation key carries the primary order quantity.
  * `ConventionsAreNotInTheObservation`: wrong readings of two unstated rules (receipts usable next day only; goods
    shipped as soon as they exist) change units at risk or the delivery day on a committed fixture for v0.2, v0.3 and
    v0.4, and the wrong unit for the percent penalty changes the penalty.

## Findings

* **F5 (v0.1).** `rules` and `state` never include the quantity of the inbound primary order. `recovery_offers`
  adds `alternate_quantity` only after the notice. Fix in v0.1 is not possible without editing an old version.
  Not implemented: v0.2 to v0.4 already show lot quantities. Recommendation: do not use v0.1 as S01.3 evidence.
* **F6 (v0.2 to v0.4).** The rule semantics are only in `docs/acceptance/` and the code. Recommendation (additive, a
  new version module, never an edit of v0.2 to v0.4): add a `conventions` block to `rules` stating
  `receipts_usable_on_arrival_day`, `production_completes_at_day_close`, `shipping_starts_on_order_due_day`,
  `shipping_priority` (tier weight, then order id), `percent_penalty_unit` (percent or basis points, per late day, on
  the undelivered part), `fixed_penalty_assessed` (once, at the due-day close), `cancellation_day_rule`. It is a
  small change (one dictionary in `observation()` of a subclass of the v0.4 world, same runner and verifier), so it
  is left as a recommendation rather than a sixth version inside an audit pull request. Status: GAP.
* **F7 (v0.2 to v0.4).** Before a firm notice of a real delay the only exact statement is a range. This is the
  intended information boundary; the tests assert the range, not an exact value.
* **Not shown.** Whether a model reads the view correctly, whether it takes the cheaper option, and whether the
  provisional prices and penalties are realistic.
