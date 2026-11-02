# Issue 8 results

Implemented `src/supplychainworld/generation.py`, `tests/test_generation.py`, and `docs/generation.md` following the recorded issue plan and agreed issue-7 registry API.

Validation: `PYTHONPATH=src python -m unittest discover -s tests -p test_generation.py -v` — 7 tests passed in 1.140 seconds. The suite verifies all eight variants against all three intended outcomes using the independent checker; seeded repeatability; private/reference exclusion; required MOQ excess; binding budget; capped rejection accounting; forged shared-template ancestry rejection; protected split public-bundle rejection; and the complete 100-instance population.

Default seed 20261102 generated 100 accepted candidates in 100 attempts, with zero construction rejections, split counts 60 train / 20 development / 20 evaluation, all three outcome types and zero cross-split overlap flags. Each accepted reference result was independently checked. Evaluation inputs and private truth were held in memory during tests; no sealed worlds or reference answers were written into public evidence. No paid calls were made.

Limits: three small synthetic structural families; no practitioner review; exhaustive enumeration suitable for these bounded worlds only; generator admission is separate from agent trajectory admission and replay. Constructor truth is never a claim of a successful agent run.
