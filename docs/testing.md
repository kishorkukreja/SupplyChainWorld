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

### S01.n  (copy for S01.1 to S01.6)

| Scenario id | Acceptance criterion (quote or link scenario-map) | Test type(s) | Test names | Status / gap |
|---|---|---|---|---|
| S01.1 | (criterion text) | P, F, E | `test_s01_property.S01KernelProperties.test_...` | covered / partial / GAP: (what is missing) |
| S01.2 | | | | |
| S01.3 | | | | |
| S01.4 | | | | |
| S01.5 | | | | |
| S01.6 | | | | |

Status of this template: EMPTY. Nothing has been mapped yet; the worked example tests only demonstrate the pattern on the S01 v0.1 modules and do not close any criterion.

## Issue #19 fixes (next diagnostic run)

- S01 v0.5 (`dynamic_v5`, `fixtures/dynamic/v0.5/`): the world shows only an opaque scenario label; same rules and numbers as v0.4.
- Stated rules: `agent_runner_v5.RULES` is the single list of every enforced rule; the eval19_v2 prompt and tool descriptions are built from it; `tests/test_eval19_v2.py` maps every rejection reason in the source to a stated sentence.
- Strict static answers: `schemas_v121` (one exact shape per kind, no repair); eval19_v2 offers one tool per kind.
- Next run harness: `eval19_v2.py` and `scripts/run_eval19_v2.py` (manifest `eval19-manifest-2`, draft until the owner commits it). The first run harness is frozen.
