# Issue 11 results

The actual offline experiment completed on 100 generated instances: 60 train, 20 development and 20 evaluation, with preassigned ancestry and a frozen private manifest before execution. Public manifest SHA-256: `67830aed77484c2f6c4c18f798ee53fa7479f1860a1b6e5680150f0050c15f42`. Cross-split overlap checks found zero lineage, exact, structural or semantic flags.

| Measurement | Actual result |
| --- | --- |
| Generated/admitted instances | 100/100; zero generation rejections |
| Expected outcomes | 34 award, 34 clarification, 32 infeasible |
| Reference baseline | 34 optimal, 34 clarification required, 32 proven capacity infeasible |
| Greedy baseline | 33 feasible, 34 clarification required, 33 error/unresolved |
| Visible-tool optimizer agent | 100 submitted, 100 independently accepted, 100 replayed |
| Observable tool actions | 634 |
| Admission | 100 accepted; three additional corrupted-hash probes rejected |
| Training export | 60 accepted train records; 40 protected dev/eval records filtered |
| Provider calls/input/output tokens | 0/0/0 |
| Provider cost | USD 0.00 |

All 100 cases cover multi-item/capacity/eligibility constraints. Primary variation coverage: 13 inventory, 13 timing, 13 MOQ, 12 fixed freight, 12 budget, 12 concentration, 12 excess, plus 13 base multi-item cases. Coverage counts indicate generated features, not independently estimated difficulty.

Actual case data, answers, baseline results, trajectories, checker/admission outputs, fixed seed, frozen manifest and training JSONL remain in `/workspace/SupplyChainWorld-private`. Public aggregate machine-readable evidence is `evidence/issue-11-summary.json`. Reproduce by retaining that private directory and rerunning `python scripts/run_smoke.py`; a fresh private directory intentionally uses a different undisclosed seed.

Validation: `PYTHONPATH=src python -m unittest tests.test_smoke -v` passed 2 integration tests, covering execution, replay/checker acceptance, private-boundary rejection, train-only exports, corrupted-hash rejection and deterministic rerun equality.

These measurements verify a deterministic offline pipeline and baselines. The tool agent uses exhaustive optimization on visible records, so its 100 accepted outputs are not evidence of LLM performance. The population uses three lineage templates with split-specific item cardinalities; the experiment does not establish broad generalization or production solver scale.
