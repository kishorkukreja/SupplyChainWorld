# Vision

Last updated: 2026-11-02  
Status: Initial project vision; implementation choices remain proposals in the [PRD](PRD.md).

## Purpose

Develop models that can perform useful supply-chain work, and establish a reliable way to measure their competence as new models become available.

The project should connect language understanding with evidence, business rules, operational tools, and measurable outcomes. A model should be able to interpret a request, find the relevant facts, calculate or plan, act within its authority, and explain its decision. When information is missing or a plan is infeasible, it should recognize that and respond appropriately.

## Two complementary products

### Supply-chain training corpus

Produce realistic, verified demonstrations for fine-tuning supply-chain models. Each example should represent meaningful work in a defined environment, with supporting evidence, observable actions, and a checked result.

An eventual corpus of approximately 500,000 examples is a possibility, not a fixed commitment. Scale should follow demonstrated improvements on unseen tasks, diversity, quality, and sustainable production cost.

### Supply-chain evaluation benchmark

Provide a repeatable way to run new models in controlled environments and grade their work. Evaluate correct execution, business outcomes, constraints, evidence, uncertainty handling, reliability, and cost.

Maintain independent evaluation content so that training gains can be distinguished from familiarity with the dataset. Publish or distribute benchmark assets only under an explicitly chosen release policy. Planning documents and the execution backlog live in the public SupplyChainWorld repository; sealed evaluation cases and answers must remain private.

## Initial focus and broader ambition

The confirmed initial context is **discrete manufacturing and distribution**.

The proposed pilot covers supplier award allocation, inventory replenishment, purchase-to-pay exceptions, and disruption replanning. These workflows expose dependencies among sourcing, inventory, production, logistics, contracts, quality, and customer commitments.

The broader ambition includes sourcing, procurement, planning, inventory, manufacturing, quality, sustainability, logistics, customer service, resilience, contracts, and other supply-chain functions. Expansion should preserve operational depth rather than adding superficial topic coverage.

## Guiding principles

1. **Ground work in evidence.** Use practitioner knowledge, documented rules, authentic source material where permitted, and clearly identified synthetic facts.
2. **Make the world coherent.** Generate related documents and system records from consistent structured business state.
3. **Verify independently.** Teacher completion and solver success are insufficient without checking the actual business requirements.
4. **Preserve legitimate uncertainty.** Clarification, escalation, and justified infeasibility findings can be correct outcomes.
5. **Evaluate consequences.** Check actions, state changes, and operational outcomes alongside written deliverables.
6. **Protect measurement integrity.** Separate training and evaluation lineages, control run configurations, and disclose benchmark versions and limitations.
7. **Scale with evidence.** Expand only when quality, transfer, coverage, and economics justify it.

## What success looks like

- Fine-tuning improves performance on independently constructed, unseen supply-chain work.
- Experts recognize the scenarios and solutions as operationally plausible.
- Graders reject convincing but incorrect answers and accept alternative valid solutions.
- Model comparisons can be reproduced and explained through task-level evidence.
- The corpus and benchmark reveal capability gaps across functions and operating conditions.
- Generation and evaluation costs are measured and support a defensible scale decision.

## Boundaries

The initial project concerns synthetic or controlled environments, not autonomous operation of live supply-chain systems. It does not assume a complete enterprise digital twin, universal industry coverage, or that one aggregate score can capture all dimensions of competence.

## Supporting documents

- [Research summary](research/2026-11-02-research-summary.md): methodological basis and source links.
- [PRD](PRD.md): proposed requirements, delivery phases, and acceptance gates.
- [Progress](progress.md): completed work, current state, decisions, and next action.
