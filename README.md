# SupplyChainWorld

Last updated: 2026-11-02

## Implemented procurement prototype

Batch 2 adds lineage-based splits, seeded task generation, an observable agent runner, replay-verified training admission/export, and an offline smoke experiment. [Batch 2 evidence](evidence/batch2.md) includes plans, reports, raw logs and screenshots for issues #7–#11. Run `python scripts/run_smoke.py --help` for the experiment interface. All case-level output belongs in an external private directory; only sanitized aggregate reports are public. The scripted optimizer is an integration baseline, not an evaluated language model.

The first implementation batch covers issues #2–#6: ten synthetic reference cases, versioned schemas, an independent checker, a bounded exact reference solver and heuristic, and a resettable procurement environment. Practitioner review remains pending. The exact solver is for small reference problems, not production-scale allocation.

Run locally with Python 3.12:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

For a source-only run with the pinned Pydantic dependency already installed, use `PYTHONPATH=src python -m unittest discover -s tests -v`.

See [execution evidence](evidence/README.md) for per-issue plans, raw results and real screenshots. CI configuration is included; its remote execution must be checked on the PR.

## Documents

- [Implementation specification](spec.md): first executable supplier-allocation milestone and technical contracts.
- [Issue roadmap](roadmap.md): dependency map and execution order.
- [Vision](vision.md): purpose, product outcomes, guiding principles, and long-term ambition.
- [Progress](progress.md): completed work, phase status, open decisions, and next action.
- [Saved research response](research/2026-11-02-research-summary.md): preserved research findings and sources, as checked on November 2, 2026.
- [PRD v0.1](PRD.md): proposed scope, requirements, phases, quality gates, risks, and decisions.

## Current state

SupplyChainWorld targets two assets: supply-chain-specific fine-tuning data, potentially 500,000 examples, and an executable benchmark for evaluating new models. Research, vision, PRD and the initial implementation specification are recorded. No dataset generation, environment implementation, or training has started.

The user confirmed **discrete manufacturing and distribution** as the initial business context. Supplier award allocation, inventory replenishment, purchase-to-pay exceptions, and disruption replanning are proposed pilot families. Budgets, owners, dates, model choices, and data access remain undecided.

## Resume here

Start with [issue #2: supplier-allocation rules and ten reference cases](https://github.com/kishorkukreja/SupplyChainWorld/issues/2). The [milestone epic](https://github.com/kishorkukreja/SupplyChainWorld/issues/1) and [roadmap](roadmap.md) track dependencies. The broader four-family pilot remains in the PRD; spec.md narrows the first executable milestone to procurement. Do not treat proposed counts or gates as approved budgets or observed results.

GitHub issues are the execution backlog. Work on issue-specific branches and PRs, link acceptance evidence, and update progress.md after substantive milestones. Sealed evaluation data and answer keys must remain outside this public repository. No external Notion or Drive project has been created or updated.
