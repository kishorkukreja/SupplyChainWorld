# Issue #22: local engineering evidence

The deterministic five-day S01 kernel in `src/supplychainworld/dynamic.py` advances time and executes receipts, recovery commitments, production, customer shipping and service assessments. It records event/state history and rejected command attempts. Observations and event histories returned to callers are copies.

Run from the repository root: `PYTHONPATH=src python -m unittest discover -s tests -v`. This branch adds five tests; their actual local output is in [issue-22-tests.log](issue-22-tests.log). The policy ledgers were generated from real runs in [issue-22-ledgers.json](issue-22-ledgers.json). They match the proposal: maintain = 4 on-time, cost 120; expedite = 12 on-time, cost 24; alternate = 12 on-time, cost 40 and 8 components left.

These tests compare with hand-worked acceptance tables. They do not replace the independent checker under #25, nor the actual agent-tool runner/replay under #24/#26. The kernel has fixed quantities, one fixture and one facility; it is not an extensible manufacturing model, general benchmark or validated training generator. No practitioner has reviewed these assumptions. No LLM or paid API was used.

Screenshot capture was not available for this work: the prior attempt to capture local document screenshots in this environment was blocked by browser administrator policy. The tests and ledger files are direct evidence; no screenshot has been invented.
