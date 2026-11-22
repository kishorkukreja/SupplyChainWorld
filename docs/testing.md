# Testing guide

Project rule (see CLAUDE.md): the main evidence is property-based, fuzz, end-to-end and browser tests. Example-based unit tests are supplementary. One runner for everything: `unittest`.

## Set up

```
python -m pip install -e ".[test]"          # adds Hypothesis and Playwright (test-only extras)
python -m playwright install chromium       # once; CI uses --with-deps
```

## Run

| What | Command |
|---|---|
| Everything (what CI runs) | `PYTHONHASHSEED=0 SCW_REQUIRE_BROWSER=1 python -m unittest discover -s tests -v` |
| Everything, skipping browser if unavailable | `PYTHONPATH=src python -m unittest discover -s tests` |
| Property tests only | `python -m unittest discover -s tests -p "test_*_property.py"` |
| Fuzz tests only | `python -m unittest discover -s tests -p "test_*_fuzz.py"` |
| End-to-end only | `python -m unittest discover -s tests -p "test_*_e2e.py"` |
| Browser only | `python -m unittest discover -s tests -p "test_*_browser.py"` |
| Deeper random exploration | `SCW_HYPOTHESIS_PROFILE=dev python -m unittest discover -s tests -p "test_*_property.py"` |

Name new files `test_<scenario>_property.py`, `_fuzz.py`, `_e2e.py`, `_browser.py` so the commands above find them.

In CI the workflow installs the test extra, installs Chromium and sets `SCW_REQUIRE_BROWSER=1`, so a missing browser fails the build instead of skipping. Screenshots from the run are uploaded as the `browser-screenshots` artifact.

## Shared helpers (`tests/support/`)

- `support/profiles.py`: Hypothesis profiles, loaded automatically by `import support`. `ci` (default): 100 examples, `derandomize=True` (same examples every run), no deadline. `dev`: 500 random examples, examples saved under `.hypothesis/examples` (gitignored). Hypothesis does not allow a database together with `derandomize`, so `ci` has none.
- `support/regression.py`: saving failing examples (below).
- `support/fuzz.py`: generators for malformed tool calls, arbitrary JSON values, valid call sequences, and damaged copies of a recorded transcript.
- `support/s01.py`: S01 fixtures, a world factory, a runner factory.
- `support/browser.py`: `BrowserTestCase` (starts Chromium, serves `evidence/` on a local port, collects console errors, saves screenshots) and a local static server.

Worked examples to copy: `test_s01_property.py`, `test_s01_fuzz.py`, `test_s01_e2e.py`, `test_s01_browser.py`.

## Adding a Hypothesis property

1. Write a strategy for the inputs (a whole action sequence, not one action). Reuse `support.fuzz` where it fits.
2. Put `@given(...)` on a `unittest.TestCase` method and `import support` at the top of the module.
3. Run the sequence step by step and assert the invariants after every step (no negative stock, conservation, budget, one commitment executes once, rejected commands leave state unchanged).
4. Also assert replay reproduces the run and the independent verifier agrees. Never use the simulator's own pass flag.

## Failing examples become regression tests

1. Run with `SCW_SAVE_FAILURES=1`. Tests that wrap their checks in `record_on_failure('name', example)` write the failing example to `tests/regressions/pending/name.json` (gitignored). Hypothesis replays the smallest failing example last, so the file holds the minimal one. The example must be JSON-serializable.
2. Fix the bug, then promote it: `python -c "import sys; sys.path.insert(0,'tests'); from support.regression import promote; print(promote('name'))"`. This writes `tests/regressions/name-<hash>.json`. Commit it.
3. A test calls `load_regressions('name')` and replays every saved example forever (see `test_saved_regressions_still_pass`). You can also copy the `@reproduce_failure` line Hypothesis prints, but the saved JSON is the durable record.

## How browser tests find the browser

- `SCW_CHROMIUM_PATH` set: that Chromium executable is launched (used in the sandbox, which has Chromium preinstalled; do not run `playwright install` there).
- Otherwise Playwright's own Chromium is used (what CI installs).
- If Playwright or the browser is missing: the tests skip with a message saying what to install, unless `SCW_REQUIRE_BROWSER` is set, in which case they fail. A skip is never a pass.
- Pages are served from a local `http.server` on 127.0.0.1 (no outside network). Screenshots are real captures saved to `test-output/browser/` (gitignored). Copy a small one into `evidence/` by hand only if it is meant as evidence. Never create or edit screenshots by other means.
- Browser tests compare what is on the page with the JSON it was generated from, and fail on any console error, uncaught page error or failed request.

## Traceability template

Fill one table per scenario. A criterion with no test is a GAP, never a pass. Status values: `covered` (all listed tests pass), `partial` (say what is missing), `GAP` (no test).

Test types: P = property (Hypothesis), F = fuzz, E = end-to-end, B = browser, U = unit (supplementary).

### Traceability for S01 (scenario-map section 4 and the contract gates G1 to G9)

Filled in by the S01 audit (evidence/s01-audit/). Test modules, all under `tests/`, abbreviated below:

- **PROP** = `test_s01_versions_property`, classes `Properties_v01` to `Properties_v04` (P, Hypothesis, generated scenarios and call sequences)
- **MUT** = `test_s01_verifier_mutation_property`, classes `VerifierMutation_v01` to `_v04` (P)
- **EQV** = `test_s01_equivalence_property` (P, a later version reduces to the earlier one)
- **ASSESS** = `test_s01_assessment_property` (P and E, S01.3 assessment from observations)
- **FUZZ** = `test_s01_versions_fuzz`, classes `RunnerFuzz_v0N`, `EarlyWarningTwins_v0N`, `ScenarioFuzz_v0N`, `RecordFuzz_v0N`, `NoticeDateIsNotLeakedEither`, `ExactOnceBoundary`, `CrossVersionFeed`, `ConstructorFuzz` (F)
- **E2E** = `test_s01_versions_e2e` (E: every fixture x every declared policy, JSON-only agent, committed evidence replay, script determinism)
- **BRW** = `test_s01_versions_browser.GeneratedPages` (B: pages generated fresh by the demo scripts, opened in Chromium)
- **REG** = `test_s01_audit_regressions` (U, pinned defects D1 to D7)
- **U** = existing example tests (`test_dynamic*.py`, `test_agent_runner*.py`, `test_dynamic_verifier*.py`, `test_dynamic_demo*.py`), supplementary only. The original worked examples `test_s01_property`, `test_s01_fuzz`, `test_s01_e2e`, `test_s01_browser` are kept unchanged.

`v0N` or `N` in a name stands for each version (v01 to v04). Status: `covered` (the listed tests pass and show the criterion with P, F, E or B), `partial` (what is missing is stated), `GAP` (no test of that part). Findings F1 to F8 and defects D1 to D7 are in `evidence/s01-audit/results.md`.

#### Sub-scenario criteria (quoted from `docs/acceptance/scenario-map.md` section 4, "State/evidence required")

| Scenario id | Acceptance criterion | Version | Types | Test names | Status / gap |
|---|---|---|---|---|---|
| S01.1 | "Business clock, material balances and customer commitment progression" | v0.1 to v0.4 | P, E, B | `PROP.Properties_v0N.test_invariants_after_every_step_and_rejections_change_nothing` (components and finished goods conserved after every step, no negative stock, shipments never above production or order quantity, penalty and shipping rules re-derived from the history, days close 1..n in order); `PROP.Properties_v0N.test_time_only_moves_forward_and_scorecard_needs_a_finished_episode`; `E2E.EveryFixtureEveryPolicy.test_run_verify_replay_and_hand_ledgers_for_all_fixtures_and_policies`; `BRW.GeneratedPages.test_v01_timeline_page_lists_every_attempt_of_every_episode`, `test_v02_timeline_page`, `test_v03_timeline_page`, `test_v04_timeline_page` | covered. The v0.2 to v0.4 timeline pages come from the new `scripts/render_s01_timeline_html.py` (the demo scripts only write `timeline.txt`). |
| S01.2 | "Existing PO arrival changes" | v0.1 to v0.4 | P, E | `PROP.Properties_v0N.test_notice_and_signal_appear_on_their_day_and_the_primary_po_moves_as_written` (the primary PO shows its promised day until the notice, then the revised day, and is received exactly once on that day); `PROP.Properties_v0N.test_replay_reproduces_state_and_scorecard_and_verifier_accepts`; `E2E.EveryFixtureEveryPolicy.test_run_verify_replay_and_hand_ledgers_for_all_fixtures_and_policies` | covered |
| S01.2 | "dated notice is visible at the correct time" (v0.2 to v0.4 also the earlier possible-delay signal) | v0.1 to v0.4 | P, F | `PROP.Properties_v0N.test_notice_and_signal_appear_on_their_day_and_the_primary_po_moves_as_written`; `FUZZ.EarlyWarningTwins_v0N.test_delay_and_no_delay_twins_have_identical_observations_until_the_firm_notice`, `test_the_delayed_arrival_date_is_not_visible_before_the_firm_notice`, `test_after_the_firm_notice_the_twins_do_differ_so_the_check_is_not_vacuous`; `FUZZ.NoticeDateIsNotLeakedEither.test_twins_with_different_notice_days_match_until_the_earlier_notice`; `ASSESS.Assessment_v0N.test_the_firm_notice_changes_what_the_agent_sees_but_the_warning_does_not` (v0.2 to v0.4) | covered. The notice-date twin test runs on the v0.3 and v0.4 runners; the v0.1 and v0.2 twin tests vary the outcome and the delayed day only. |
| S01.3 | "Agent can inspect requirements, inventory, capacity and available recovery terms" | v0.1 | P, E | `ASSESS.V01ObservationsAreInsufficient.test_scenarios_differing_only_in_the_primary_quantity_look_identical_until_the_receipt`, `test_witness_the_two_scenarios_have_different_outcomes`, `test_no_observation_field_carries_the_primary_quantity` | **partial (finding F5)**: requirements, inventory, capacity and recovery terms are visible; the size of the inbound supplier order is not, so exposure cannot be determined. Not fixable in v0.1 (old versions stay as they are). |
| S01.3 | same | v0.2, v0.3, v0.4 | P, E | `ASSESS.Assessment_v0N.test_assessment_from_observations_matches_the_verifier_on_generated_scenarios`, `test_every_fixture_every_decision_day_every_option`, `test_zz_the_generated_runs_made_exact_and_bounded_comparisons_for_every_option` (N=2..4) | **partial**: every quantity is observable and an assessor reading only the view equals the verifier's ground truth (exact after the firm notice, bounds before it). Missing: the rules that turn quantities into outcomes are not stated in any observation (F6, GAP; recommendation in `evidence/s01-audit/s01-3-assessment.md`). |
| S01.3 | "S01.3 needs evidence that the tool observations support impact assessment. A scripted baseline may calculate that impact without implying a real LLM has demonstrated the skill." | v0.1 to v0.4 | P | `ASSESS.ConventionsAreNotInTheObservation.test_a_wrong_guess_about_an_unstated_rule_changes_the_answer`, `test_penalty_rate_units_differ_between_versions_and_are_not_in_the_observation` | **partial**: the assessor is a test script and no model was run; no claim about model ability is made or supported. |
| S01.4 | "Real PO/event/budget change" | v0.1 to v0.4 | P | `PROP.Properties_v0N.test_invariants_after_every_step_and_rejections_change_nothing` (includes the effect of every accepted commitment on the PO lots, the event and the spend, and the budget never exceeded); `EQV.V4EqualsV3WithoutAlternateSupply.test_spend_differs_by_exactly_the_base_cost_of_alternate_units`; `EQV.V2EqualsV1ForOneOrderAndWholeLotRecovery.test_same_flows_costs_and_scorecard` | covered |
| S01.4 | "valid authority" | v0.1 to v0.4 | P, F | `FUZZ.RunnerFuzz_v0N.test_calls_that_need_an_authority_that_was_not_granted_are_refused_and_change_nothing`; `PROP.Properties_v0N.test_commitments_beyond_the_budget_or_outside_the_window_are_refused_with_no_effect`; `FUZZ.RunnerFuzz_v0N.test_malformed_calls_are_rejected_state_unchanged_no_hidden_names` | covered. "Authority" in the code means the granted tool classes and the budget; there is no approval workflow to test. |
| S01.4 | "exact-once execution" | v0.1 | P | `PROP.Properties_v01.test_an_executed_commitment_cannot_be_executed_again`; `PROP.Properties_v01.test_invariants_after_every_step_and_rejections_change_nothing` | covered (one recovery per episode) |
| S01.4 | same | v0.2, v0.3, v0.4 | P, F | `PROP.Properties_v0N.test_an_executed_commitment_cannot_be_executed_again` (with an `action_id`); `FUZZ.ExactOnceBoundary.test_the_same_commit_twice_without_an_action_id_executes_twice_and_with_one_only_once` | **partial (finding F4)**: exact-once holds only when the caller supplies an `action_id`; the same call re-sent without one is a second purchase. |
| S01.5 | "Actual receipts, production, shipments and penalties across the horizon" | v0.1 to v0.4 | P, E, B | `PROP.Properties_v0N.test_invariants_after_every_step_and_rejections_change_nothing`; `MUT.VerifierMutation_v0N.test_valid_runs_are_accepted_and_every_history_mutant_is_rejected`; `E2E.EveryFixtureEveryPolicy.test_run_verify_replay_and_hand_ledgers_for_all_fixtures_and_policies` (hand-worked ledgers); `EQV.V3EqualsV2WhenV03FeaturesAreOff.test_same_state_after_every_call`; `BRW.GeneratedPages.test_v01_report_scorecard_and_timeline_match_the_source_json`, `test_v02_report_per_metric_blocks_and_gates`, `test_v03_report_per_metric_blocks_and_gates`, `test_v04_report_per_metric_blocks_and_gates` | covered |
| S01.6 | "Independent ledger checks" | v0.1 to v0.4 | P, F | `PROP.Properties_v0N.test_replay_reproduces_state_and_scorecard_and_verifier_accepts`, `test_verifier_accepts_every_valid_partial_run`; `MUT.VerifierMutation_v0N.test_valid_runs_are_accepted_and_every_history_mutant_is_rejected`; `FUZZ.RecordFuzz_v0N.test_verifier_survives_garbage_history_scorecard_and_actions`, `test_verifier_survives_event_shaped_garbage_and_never_accepts_it_as_a_complete_episode`, `test_a_history_with_a_hole_or_a_swap_is_never_accepted_as_complete`; `FUZZ.ScenarioFuzz_v0N.*`; `REG.D1` to `REG.D6` | covered. The rule that the verifier imports no simulator code is enforced by the existing AST unit tests (`test_dynamic_verifier*.py`, U), not by a property. |
| S01.6 | "scenario scorecard" (and the policy comparison in the S01.6 title) | v0.1 to v0.4 | E, P, B | `E2E.EveryFixtureEveryPolicy.test_run_verify_replay_and_hand_ledgers_for_all_fixtures_and_policies` (the scorecard read through the tool equals the verified one); `MUT.VerifierMutation_v0N.test_changed_scorecard_or_action_log_is_rejected`; `BRW.GeneratedPages.test_v01_report_scorecard_and_timeline_match_the_source_json`, `test_v02_report_per_metric_blocks_and_gates`, `test_v03_report_per_metric_blocks_and_gates`, `test_v04_report_per_metric_blocks_and_gates` | covered |
| S01.6 | "replay" | v0.1 to v0.4 | P, F, E | `PROP.Properties_v0N.test_replay_reproduces_state_and_scorecard_and_verifier_accepts`; `FUZZ.RecordFuzz_v0N.test_damaged_transcripts_replay_to_a_refusal_or_a_difference_never_a_silent_pass`; `FUZZ.CrossVersionFeed.test_a_transcript_of_one_version_is_refused_by_every_other_versions_replay`; `E2E.CommittedEvidenceStillReplays.test_committed_transcripts_replay_and_match_committed_scorecards` | covered |
| S01.6 | "readable experience" | v0.1 to v0.4 | E (determinism only), U | `E2E.DemoScriptsRegenerateCommittedEvidence.test_every_generated_file_equals_the_committed_file` (the experience record files regenerate byte for byte); the no-leak scan of the record in `test_dynamic_demo*.py` (U) | **GAP for readability**: no property, fuzz or browser test judges whether the experience record (`experience-record.md`, `.json`) is readable, and no page renders it. The content is reproducible and leak-scanned; readability is a human judgement not yet made. |
| (cross-version) | "v0.2 to v0.4 reduce to the earlier version's behavior where the rules say they should" (an audit requirement, not in the map) | v0.2 to v0.4 | P | `EQV.V4EqualsV3WithoutAlternateSupply.*`, `EQV.V3EqualsV2WhenV03FeaturesAreOff.*`, `EQV.V2EqualsV1ForOneOrderAndWholeLotRecovery.*` | covered |

#### Contract gates G1 to G9 (`docs/acceptance/dynamic-supplier-delay-v0.1.md` section 6, "Required proof")

| Gate and required proof (quoted) | v0.1 | v0.2 | v0.3 | v0.4 | Types | Test names and gap |
|---|---|---|---|---|---|---|
| G1 Coherent initial world: "Inspectable entities, commitments, rules, seed/calendar version and visibility definition" | partial | partial | partial | partial | E, F | `E2E.JsonOnlyToolAgent.test_a_json_only_agent_completes_every_fixture_and_the_result_verifies`; `FUZZ.RunnerFuzz_v0N.test_no_hidden_scenario_field_name_appears_in_any_observation_or_result`. Missing: no property asserts the schema and runtime version labels or a written visibility definition. v0.1 also lacks the inbound order quantity (F5). |
| G2 Actual time progression: "Log shows opening1 through close5, not a constant simulated_time field" | covered | covered | covered | covered | P, B | `PROP.Properties_v0N.test_invariants_after_every_step_and_rejections_change_nothing` (day closes 1..n in order, history days never go back); `PROP.Properties_v0N.test_time_only_moves_forward_and_scorecard_needs_a_finished_episode`; `BRW.GeneratedPages` timeline tests |
| G3 Executed disruption and recovery: "Delay changes the primary event; expedite reschedules that PO; alternate creates a distinct PO while preserving the original" | covered | covered | covered | covered | P | `PROP.Properties_v0N.test_notice_and_signal_appear_on_their_day_and_the_primary_po_moves_as_written`; `PROP.Properties_v0N.test_invariants_after_every_step_and_rejections_change_nothing` (`check_commit_effects`: expedite moves the lot to the offered day, alternate adds a separate lot, existing lots are unchanged) |
| G4 Consequential state changes: "Inventory, scheduled releases, completions, shipments, budget and penalties reconcile at each step" | covered | covered | covered | covered | P | `PROP.Properties_v0N.test_invariants_after_every_step_and_rejections_change_nothing`; `EQV.*` |
| G5 Baseline differences: "Run all three declared policies under the same initial world/event and match both tables above" | covered | covered | covered | covered | E, B | `E2E.EveryFixtureEveryPolicy.test_run_verify_replay_and_hand_ledgers_for_all_fixtures_and_policies`; `E2E.EveryFixtureEveryPolicy.test_v01_policies_order_as_the_written_acceptance_tables_say`; `BRW.GeneratedPages.test_v01_report_scorecard_and_timeline_match_the_source_json`. The hand-worked tables are fixed examples, so this proves the committed cases only; v0.2 to v0.4 declare five policies, not three. |
| G6 Independent checking: "Check component/finished-goods conservation, order quantities, timing, capacity, budget and unique execution without trusting the simulator's own pass flag" | covered | covered | covered | covered | P, F | `MUT.VerifierMutation_v0N.*` (including `test_self_reported_pass_flags_never_change_the_verdict`); `FUZZ.RecordFuzz_v0N.*`; `REG.D2`, `REG.D3` |
| G7 Failure behavior: "Reject premature receipts, overproduction, production without material, over-budget/late recovery and duplicate commitments; no operational mutation on rejection" | covered | covered | covered | covered | P, F | `PROP.Properties_v0N.test_invariants_after_every_step_and_rejections_change_nothing` (every rejected command leaves state unchanged; releases beyond capacity, material and demand are drawn); `PROP.Properties_v0N.test_commitments_beyond_the_budget_or_outside_the_window_are_refused_with_no_effect`; `PROP.Properties_v0N.test_an_executed_commitment_cannot_be_executed_again`; `FUZZ.RunnerFuzz_v0N.*`. Premature receipts are not agent actions; the verifier rejects them (`MUT.VerifierMutation_v0N` day-shift mutants). |
| G8 Replay and data: "Replaying the same recorded actions reproduces the state sequence and scorecard; produce one inspectable observable episode with private answers excluded" | covered | covered | covered | covered | P, F, E | `PROP.Properties_v0N.test_replay_reproduces_state_and_scorecard_and_verifier_accepts`; `FUZZ.RecordFuzz_v0N.test_damaged_transcripts_replay_to_a_refusal_or_a_difference_never_a_silent_pass`; `FUZZ.EarlyWarningTwins_v0N.*`; `FUZZ.RunnerFuzz_v0N.test_no_hidden_scenario_field_name_appears_in_any_observation_or_result`; `E2E.DemoScriptsRegenerateCommittedEvidence.test_every_generated_file_equals_the_committed_file` |
| G9 Honest demonstration: "Label scripted policies, assumptions, practitioner-review status and remaining limitations; screenshots complement traces and checks" | covered (labels) | covered (labels) | covered (labels) | covered (labels) | B | `BRW.GeneratedPages` (the page shows PROVISIONAL, no LLM, reviewed: no, G9 as Partial, and no overall winner); real screenshots in `evidence/s01-audit/screenshots/`. The gate stays open by design: no practitioner review has happened. |

Status summary: S01.1, S01.2 and S01.5 covered. S01.3 partial (v0.1 insufficient; v0.2 to v0.4 quantities sufficient, rule statements missing). S01.4 covered except exact-once for v0.2 to v0.4 (partial). S01.6 partial (experience-record readability is a GAP). Nothing here is practitioner-reviewed, and these are software tests of synthetic provisional rules, not evidence of model ability.
