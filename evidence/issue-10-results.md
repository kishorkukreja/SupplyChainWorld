# Issue 10 results

Implemented `src/supplychainworld/admission.py`, `tests/test_admission.py`, and `docs/admission.md`. Dependencies were coordinated directly with lineage, generation and runner owners. Runner trajectories use one initial observation plus one after every action; replay admission compares that complete sequence and exact rendered-artifact hashes.

Validation on 2026-11-02:

- `PYTHONPATH=src python -m unittest discover -s tests -p test_admission.py -v`: 7 tests passed.
- `PYTHONPATH=src python -m unittest discover -s tests -v`: all 57 tests passed, including batch integration and smoke checks available at execution time.

Tests demonstrate clean JSONL/loss serialization, rejection of injected expected metadata, changed action results and hashes, wrong cost/submission, wrong declared split, mixed-split lineage, duplicate tasks, post-admission message mutation, train-only export and refusal to repair an agent mistake or reduce demand. Export reconstructs admission again against current task/world and retained deep-copied trajectory before writing. Entire-batch overlap validation occurs before any file write.

Failure diagnosis is an explicit evidence classification API; it cannot infer whether a grader is correct. Bounded repair defaults to no business-state changes and allows only expressly named artifact/tool-profile corrections. It cannot repair solver mistakes or weaken demand, constraints, type or lineage. Repair probes are caller callbacks: the helper records invocation, not proof of isolation; actual training admission always independently reconstructs and replays an isolated environment. No practitioner endorsement, model-training improvement or paid model evidence is claimed.
