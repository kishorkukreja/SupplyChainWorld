# SupplyChainWorld vision

Updated: 2026-11-15
Status: User intent restated after an alignment audit. Detailed simulator design and acceptance scenario still require review.

## Purpose and the two products

Create realistic, verifiable supply-chain experiences that support:
1. A high-quality training corpus for fine-tuning supply-chain models, potentially reaching approximately 500,000 useful examples if evidence justifies that scale.
2. An independent supply-chain benchmark in which new models operate in configured environments and are graded on their behavior and business outcomes.

Initial business context confirmed by the user: discrete manufacturing and distribution. Broader coverage includes sourcing, procurement, planning, inventory, manufacturing, quality, sustainability, logistics, customer service, resilience, contracts and related functions.

The original request was research first: investigate WorkFactory and related task/environment/solver methods, establish what is valid and realistic, and then plan implementation. Later conversation explicitly confirmed world-building, situations and simulation as the intended mechanism. Do not rewrite the original request as a demand for a particular simulator architecture.

## Required approach

**World → executable environment → situation → actions and observations over time → simulated consequences → independent verification → training experience or benchmark result.**

- **World:** Coherent business entities and relationships: suppliers, materials/products, facilities, inventory, orders, commitments, resources and commercial rules. The initial world can be small.
- **Environment:** Executable transition rules and tools. Actions can change business state; the environment determines valid actions, information visibility, timing and consequences.
- **Situation:** A grounded problem introduced into that world, such as a supplier delay threatening a production or customer commitment.
- **Simulation:** Time advances and scheduled events occur. Inventory, arrivals, material consumption, capacity, demand or commitments evolve under explicit assumptions.
- **Agent experience:** The agent inspects permitted evidence, chooses actions, observes consequences and adjusts. It may clarify or escalate when warranted.
- **Verification:** Independent checks establish conservation, feasibility, permissions, costs, service and other relevant outcomes throughout the episode.
- **Dataset/benchmark:** Record the observable interaction with provenance. Admit verified demonstrations to training, and keep independent evaluation situations separate.

Analytical and static tasks may be useful supporting components. They do not, by themselves, demonstrate the dynamic world and situation lifecycle above.

## Training and evaluation

Training examples should be grounded in valid situations and verified outcomes, with source and generator provenance. Solvers, heuristics, teacher agents and practitioner review have complementary roles. A teacher must use only information available to the eventual model; hidden future events and grader answers must not leak into demonstrations.

Benchmark tasks must run under declared environment versions, visibility boundaries, tool access and budgets. Report operational outcomes, constraint violations, uncertainty handling, reliability and cost. Distinguish model capability from the capabilities supplied by a solver or harness.

A simulator that is internally consistent is not automatically representative of real supply-chain work. Record assumptions and actual practitioner-review status. A high synthetic acceptance rate is not evidence of generalization or learning value.

## Required next demonstration

Before further teacher-corpus collection or expanding the product scope, demonstrate one bounded dynamic situation end to end:
- Inspect a small initial manufacturer/supplier/inventory/order world.
- Introduce a disruption at a defined point in simulated time.
- Allow an agent to take a valid operational action.
- Advance time and apply delayed consequences.
- Show changed inventory, commitments, production or service outcomes.
- Compare with a declared baseline under the same exogenous conditions.
- Independently verify and replay the complete episode.
- Inspect the experience that would be eligible for training or evaluation.

The exact entities, horizon, actions, disruption and business metrics are not yet agreed. Any numerical example or scenario offered during planning is a proposal, not an approved requirement.

## Current reality

The repository contains a static, single-period supplier-allocation prototype. Its tools retrieve evidence and record a recommendation or exception. They do not execute purchases or advance a supply-chain timeline.

PR #15 is merged. PR #16 is open as of this update and contains additional generation/runner/export infrastructure. Its recorded offline smoke experiment reported 100 static episodes and 60 train-split exports from a scripted visible-input optimizer. These are engineering test demonstrations, not an accepted domain corpus, dynamic simulation evidence or measured fine-tuning gains.

Useful code can be retained and adapted after review. Do not infer alignment from issue completion, passing tests, screenshots, a repository name or the presence of a field named simulated_time.

## Alignment rules for future work

1. Read this file and the latest audit before proposing or starting work.
2. Map each milestone and issue to a user requirement and an observable acceptance behavior.
3. Identify the assumptions being introduced and the requirements being deferred. Do not silently replace operational simulation with a static exercise.
4. Separate user-confirmed decisions, assistant proposals, implemented behavior, verified behavior, practitioner review and measured model improvement.
5. Show evidence for the goal as well as evidence that the code satisfies its local specification.
6. Treat changes to the core workflow or milestone sequence as explicit, reviewable scope decisions.
7. Preserve historical work and findings; do not relabel static records as dynamic experiences.
8. Follow the user's current instruction. At this stage the authorized work is the audit and vision publication; further implementation is paused pending reconciliation.

## Documents and authority

[Alignment audit](docs/audits/2026-11-15-alignment-audit.md) records findings and proposed dispositions of existing issues. The existing [PRD](PRD.md), [specification](spec.md), [roadmap](roadmap.md) and GitHub issue sequence contain unreconciled historical assumptions. They are not authority to resume the old sequence automatically.

If documents conflict, surface the conflict against the user's latest instruction. This vision records intent; it does not retroactively approve a new technical architecture or authorize bulk generation, paid calls, merging PR #16 or training.
