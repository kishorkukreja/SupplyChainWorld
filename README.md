# SupplyChainWorld

Last updated: 2026-11-02

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
