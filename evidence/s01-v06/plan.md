# S01 v0.6 plan (issue #19, audit follow-up)

Owner instruction: build S01 v0.6 as a NEW version beside v0.5, with no live model call (mocked transports only). All numbers
PROVISIONAL, needs practitioner value; no practitioner review (owner review only, not independent); no claim about model ability.

1. Rebuilt independent checker (`dynamic_verifier_v6`): close audit defects D2 to D6 that the frozen v0.4 and v0.5 checkers still have
   (opening records and their order, the full recorded state including schema and runtime version, non-mapping records, malformed
   scenario parts, malformed action logs) and make exact-once hold when the caller sends no action id. Same mutation and garbage-history
   campaign as the audit, before (v0.5 checker) and after (v0.6 checker).
2. Conventions block in the agent-visible rules, stated from the world itself, with an assessor test that uses only the agent view.
   Rules-in-prompt consistency test extended to every v0.6 refusal.
3. Demonstration packet, report page, real browser test with a screenshot, determinism test, readability check (structural, honest about
   its limits), hand-worked ledgers for 25 episodes from a committed generator with no project imports.
4. docs/testing.md traceability for v0.6. A DRAFT eval19-3 note and module as new files only; the frozen first diagnostic and eval19-2
   files and hashes are untouched. The diagnostic was not run.

Branch `implementation/s01-v06`, one commit per item, PR to `main` with `Refs #19`, not merged.
