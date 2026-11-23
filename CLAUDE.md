# CLAUDE.md

Project guide for AI agents working in SupplyChainWorld. Read `vision.md`, `progress.md` and `docs/acceptance/scenario-map.md` before substantial work.

## What this project is

An executable, verified supply chain world: simulated operating situations (S01 supplier delay and later S02 to S07), tools an agent acts through, an independent verifier, replay, and evidence. Everything is synthetic, offline by default, and all numeric business values are provisional until a practitioner confirms them.

## Testing rule (primary, applies to all new and changed work)

The primary testing functions are, in this order of importance:

1. **Property-based tests** (Hypothesis). State invariants over generated inputs and action sequences, not hand-picked examples. Examples: conservation of components and finished goods, no negative stock, budget never exceeded, each commitment executes at most once, replay of any recorded run reproduces state exactly, verifier accepts every valid run and rejects every tampered one.
2. **Fuzz tests.** Feed malformed, out-of-order, duplicated, extreme or adversarial inputs (actions, tool arguments, transcripts, fixtures, model outputs) and assert the system rejects cleanly, leaves state unchanged, and never crashes or leaks hidden state.
3. **End-to-end integration tests.** Run a whole episode through the real tool interface, runner, simulator, independent verifier and replay, using the same entry points a real agent or script uses. Mocked transports only at the network edge.
4. **Browser-based tests** (Playwright). Load the generated report, timeline and evidence pages in a real browser and assert that what a person sees matches the data, with real screenshots as evidence. Do not generate or fake screenshots.

Example-based unit tests are supplementary: use them for pinned regressions, hand-worked ledgers and exact edge cases, not as the main evidence.

Rules that follow:
- Every scenario and sub-scenario has a traceability entry mapping each acceptance criterion in the scenario map to the tests that prove it. A criterion with no test is reported as a gap, never as passing.
- A change is not done until the relevant property, fuzz and end-to-end tests exist and pass. Browser tests are required whenever a user-visible page or report changes.
- The verifier must stay independent of the simulator: do not import simulator transition code into it, and keep the AST test that enforces this. Never trust a simulator's self-reported pass flag.
- Hypothesis runs must be reproducible: fixed seed in CI, and failing examples saved as regression tests.
- Report test status honestly: say what was implemented, what was tested, what was reviewed by a practitioner. Do not claim model ability, generalization or training value from software tests.

## Conventions

- Add new versions beside old ones (for example `*_v4`); do not edit earlier versions, fixtures or evidence.
- Label every unconfirmed business number PROVISIONAL, needs practitioner value. Practitioner review so far is owner review, not independent.
- OpenRouter: free-tier models only, with a $0 ceiling, through the existing adapter (`llm_adapter`). Sarvam is paid, through `sarvam_adapter` only, with a hard cap of INR 10000 per run, stated in the committed test plan before any call. No other paid model calls. Never print, log or commit credentials.
- Keep sealed or private evaluation data, answer keys and hidden scenario parameters out of anything an agent or model can see, and keep a no-leak test for each new view.
- Run the suite with `PYTHONPATH=src python -m unittest discover -s tests` (Python 3.12 in CI). Browser tests and Hypothesis tests are part of the default suite once the dev dependencies are installed.
- Each issue gets its own branch and PR to `main`; merge only with green CI and a review of the diff, secrets and blast radius.
