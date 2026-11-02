# Supply-chain training data and benchmark: research summary

Saved: 2026-11-02. This file preserves the preceding research response for future reference. Source availability and research claims reflect the checks made on that date; implementations were not run.

---

**My recommendation is to build a shared supply-chain environment and validation system, then use it to produce two separate assets: verified training trajectories and an independently curated benchmark.** WorkFactory supplies useful ideas for generating tasks, but it does not supply everything needed for trustworthy supply-chain evaluation.

I reviewed its paper’s methodology and relevant appendices, inspected the public repository, and compared related research on workplace task generation, agent environments, and supply-chain benchmarks. This is a research synthesis; I have not generated datasets or implemented environments.

The findings below distinguish published methods from my recommendations.

**WorkFactory is relevant—but its public repository is not yet a runnable starting point.**

As checked on November 2, 2026, the repository contains a README, license, and presentation assets. The dataset and model links are placeholders, including a TODO to replace them with Hugging Face URLs. There is no task-generation implementation in the inspected tree. We can adapt its published method, but cannot currently assume we can clone the repository and run its pipeline. [Repository](https://github.com/IQuestLab/WorkFactory)

Its central method is:

1. Identify a professional objective.
2. Work backward from the deliverable to the information needed.
3. Build an **information support graph** connecting premises, dependencies, and their locations.
4. Materialize the workspace.
5. Have a separate agent attempt the task using only visible inputs.
6. Repair blocking defects without supplying the answer or removing the substantive work.
7. Collect an independent teacher trajectory.

The paper reports 112,686 tasks across 612 occupations. However, its repair process targets blockers; nonblocking correctness errors can remain, and trajectory filtering is comparatively lightweight. **Executability is therefore not a correctness guarantee.** [WorkFactory paper](https://arxiv.org/html/2610.37161v1)

For our purposes, that last limitation is crucial. A supplier-selection workbook can be complete, readable, and convincingly explained while using the wrong freight basis.

**Several complementary methods are worth borrowing.**

| Research | What it contributes | Relevance to our project |
|---|---|---|
| [GraphForge](https://arxiv.org/html/2609.38923v1) | Builds evidence graphs over real files; derives tasks and source-linked evaluation criteria from them. | Ground procurement, contracts, quality, and sustainability tasks in actual evidence. |
| [WorkGenesis](https://arxiv.org/html/2609.39325v1) | Combines real source artifacts with synthetic companion materials; attributes failures to the agent, task, or rubric. | Prevent a flawed task or grader from being mistaken for model failure. |
| [AgentGen](https://arxiv.org/abs/2408.00764) | Generates environments, then tasks within them; varies task difficulty in both directions. | Create controlled variation in planning complexity, rather than merely paraphrasing prompts. |
| [AgentGym](https://github.com/Hazyuan/AgentGym) | Provides common interfaces for interacting with environments, collecting trajectories, training, and evaluating agents. | A candidate orchestration framework, with custom supply-chain environments still required. |
| [OR-Gym](https://arxiv.org/abs/2008.06319) | Implements operations-research environments and compares RL against optimization and heuristic methods. | A foundation for inventory, routing, packing, and network decisions. |
| [τ-bench](https://arxiv.org/abs/2406.12045) | Evaluates policy-guided tool use through resulting database states and repeated-run reliability. | Procurement approvals, order changes, returns, and customer-service workflows. |
| [AppWorld](https://arxiv.org/abs/2407.18901) | Uses programmatic state tests that allow different valid solutions and check unintended changes. | Verify that an agent completed the intended action without corrupting other business records. |

I could not confidently identify the specific “GymBench” you remember. **AgentGym, OR-Gym, and AgentGen are distinct, relevant candidates**: respectively, infrastructure for interaction, operational simulations, and environment/task synthesis.

These methods also expose an important design choice. We can start with a business objective and construct its supporting world, or start with authentic evidence and derive feasible tasks. I recommend using both, with a common verification standard.

**There is already meaningful supply-chain benchmark work.**

A new benchmark needs a clear contribution beyond being supply-chain-specific.

| Existing benchmark | What it evaluates | What remains available for us to contribute |
|---|---|---|
| [SupChain-Bench](https://arxiv.org/html/2602.07342v1) | Domain QA and long tool workflows over simulated supply-chain records, with and without SOP guidance. Tool evaluation compares retrieved information against an oracle-generated set. | Broader operational state changes, optimization quality, and consequences over time. |
| [InventoryBench](https://github.com/TianyiPeng/InventoryBench) | 1,320 inventory instances using synthetic and real demand; compares OR-only, LLM-only, and two LLM–OR combinations. | Cross-functional decisions linking inventory to sourcing, production, service, and contracts. |
| [CSCBench](https://arxiv.org/abs/2601.01825) | More than 2,300 single-choice questions on commodity supply-chain reasoning, including commodity-specific rules. | Executable work and actions; its process/commodity/reasoning taxonomy is useful for coverage. |
| [E-Commerce Bench](https://ecbench.github.io/) | Long-horizon procurement, negotiation, inventory, fulfillment, returns, and cash management. | Broader industrial operations and independently varied business worlds. Its deterministic negotiation mechanism is particularly relevant to reproducibility. |

SupChain-Bench offers a useful generation pattern: execute an expert-defined SOP to obtain grounded information, then generate a question requiring that information. But retrieving the right facts does not establish that a model can make a good allocation decision or execute a purchase correctly.

InventoryBench supplies another useful lesson: **compare the model with conventional operational methods, and test how well it uses those methods.** Its inventory formulation also has explicit simplifying assumptions, including uncensored demand. We would need to examine such assumptions before treating any simulator as representative of a target business. [InventoryBench formulation](https://arxiv.org/html/2602.12631v1)

My assessment is that a defensible opportunity remains: **a benchmark combining broad functional coverage, realistic evidence, executable workflows, and business-outcome evaluation.** This is a proposed positioning, not a claim that no overlapping benchmark exists.

**We should use three kinds of environments.**

A single environment type will not adequately cover the scope you described.

| Environment | Suitable work | Primary verification |
|---|---|---|
| **Document and analytical workspace** | RFQ comparisons, spend analysis, contract interpretation, quality investigations, emissions calculations | Independently recomputed results, evidence references, document-specific criteria |
| **Stateful business system** | Purchase orders, inventory transfers, cancellations, quality holds, returns, approval routing | Database state, event history, permissions, and business invariants |
| **Operational simulator** | Replenishment, scheduling, allocation, transport, disruptions, capacity planning | Feasibility, cost, service, risk, and performance against baselines |

These can share a business model: suppliers, products, facilities, bills of material, orders, shipments, inventory lots, contracts, and calendars.

**My recommendation is to generate structured business facts first, then render the documents and interfaces from those facts.** Independently asking an LLM to invent a quotation, purchase order, shipment record, and invoice creates unnecessary opportunities for contradictions.

A shared source of truth lets us deliberately introduce realistic discrepancies—for example, an invoice overcharge—while retaining an authoritative explanation and a reliable grader.

**“Valid task” needs a stricter definition than “the teacher solved it.”**

For both datasets, I would require the following:

- **Business validity:** A practitioner recognizes the objective, constraints, and deliverable as plausible.
- **Information validity:** Necessary facts are available, discoverable, or explicitly unknown.
- **Numerical validity:** Units, dates, currencies, capacities, lead times, and accounting relationships are consistent.
- **Execution validity:** Tools and state transitions behave as specified.
- **Grading validity:** The verifier accepts legitimate alternatives and rejects plausible-looking mistakes.

There is an important exception to “all facts must be available.” Some valuable tasks should intentionally require clarification, escalation, or a finding that no feasible plan exists.

For example, an absent freight term can mean either:

- The generator accidentally produced an unsolvable cost-comparison task; or
- The task deliberately tests whether the agent requests clarification before awarding business.

Those must have different specifications and grading rules. Otherwise, a repair pipeline can accidentally remove the very judgment we want to teach.

Solver-backed tasks also require independent checking. An optimization solver can solve the wrong mathematical formulation perfectly. We should verify the resulting business decision against the original constraints, not merely accept the solver’s success status.

**The functional coverage should extend beyond topic labels.**

The following are proposed task families, not generated dataset examples:

| Function | Representative family | What establishes correctness |
|---|---|---|
| Sourcing | Allocate awards across qualified suppliers | Landed cost, capacity, qualification, concentration limits |
| Procurement | Resolve invoice/receipt/PO discrepancies | Matching rules, tolerances, approval state |
| Planning | Build a constrained production and supply plan | Material balances, calendars, capacity, demand priorities |
| Inventory | Replenish across locations | Inventory dynamics, service, holding cost, expiry |
| Manufacturing | Reschedule after downtime | Routing precedence, setups, resources, due dates |
| Quality | Contain a defective supplier lot | Traceability, affected inventory, hold/release authority |
| Sustainability | Compare sourcing or transport emissions | Defined boundaries, dated factors, units, evidence |
| Logistics | Route deliveries with constraints | Capacity, time windows, eligibility, cost |
| Customer service | Resolve an order exception | Available-to-promise state, policy, commitments |
| Resilience | Replan after a supplier or transport disruption | Recovery, service loss, alternatives, cost |
| Contracts | Apply pricing and obligation clauses | Effective dates, precedence, quantities, clause evidence |

Variation should include industry, network structure, information quality, uncertainty, decision horizon, and interacting constraints. Changing supplier names and quantities alone does not create substantial diversity.

**For training, the unit should be a verified episode—not just a question–answer pair.**

An episode should contain the initial environment, request, available tools, observations, actions, final artifact or state, and verification results.

The generation process I recommend is:

1. Establish practitioner-reviewed task families and business rules.
2. Assign scenario families and source lineages to training or evaluation before expansion.
3. Generate consistent business states and supporting artifacts.
4. Construct reference calculations, policies, or solver solutions where appropriate.
5. Probe tasks and diagnose environment defects.
6. Collect independent teacher demonstrations.
7. Replay and verify those demonstrations.
8. Admit examples based on quality and coverage, preserving provenance.

We should retain verified recovery behavior and appropriate requests for clarification. Unsuccessful trajectories can support separate preference or error-analysis datasets, but should not quietly enter a successful-demonstration corpus.

**500,000 should remain a scaling hypothesis.** Count unique task families, worlds, instances, trajectories, and training sequences separately.

The cost implications are substantial: WorkFactory reports **11.656 million construction-stage tokens per attempted task**. Directly extrapolated to 500,000 attempts, that is roughly **5.83 trillion tokens**, before separate teacher collection and training. This is an illustrative extrapolation, not a project estimate; caching, acceptance rates, and generation strategy matter enormously. [Construction-cost appendix](https://arxiv.org/html/2610.37161v1#A4.SS2)

A more economical approach may combine reusable validated generators with selectively authored complex scenarios. A pilot must establish cost per **accepted, useful** example and whether additional examples improve held-out performance.

**For evaluation, the benchmark must measure a controlled model–environment system.**

To compare each newly released model fairly, freeze:

- Environment and tool versions.
- Task inputs, source snapshots, and business rules.
- Agent instructions, memory behavior, and tool access.
- Token, time, and action budgets.
- Evaluation seeds and grading logic.

A fixed agent configuration helps isolate model differences. A separate track can allow each model its best configuration; those results answer a different question.

I recommend reporting distinct scores for:

- Correct task completion.
- Hard-constraint and policy violations.
- Business performance: cost, service, waste, emissions, or recovery.
- Evidence quality and uncertainty handling.
- Repeated-run reliability.
- Inference cost and latency.

For stochastic tasks, compare agents on matched exogenous scenarios and report uncertainty. A perfect-foresight solution can be an upper bound, but must not be presented as an attainable policy with the same information as the agent.

Do not reduce everything immediately to one leaderboard number. High average profit should not conceal unauthorized purchases or poor quality containment.

**Training–evaluation separation must be designed into generation.**

A random split of 500,000 generated rows is insufficient. Closely related scenarios can leak across the split despite different wording.

Hold out combinations of business worlds, source documents, workflow structures, network topologies, and operating regimes. Preserve both:

- A fixed, private evaluation set for longitudinal comparison.
- Periodically refreshed, independently reviewed challenges for contamination resistance.

Fresh random seeds alone do not establish generalization. The benchmark also needs human-authored cases and a smaller set grounded in actual operational examples, where permission and access allow.

**The next step should be a focused design decision, followed by a small validation pilot.**

Based on this research, I would prioritize four initial families: supplier award allocation, inventory replenishment, purchase-to-pay exception handling, and disruption replanning. Together they exercise documents, system actions, optimization, and uncertainty.

Before large-scale generation, we should settle the initial industries, model/tool setup, available real-world evidence, and meaning of “500,000 examples.” Then validate a modest set of task families with domain experts, conventional baselines, and multiple models.

The pilot’s acceptance questions should be concrete: Are the tasks realistic? Do the graders catch wrong answers? Can different valid solutions pass? Does fine-tuning improve unseen scenarios? What does each accepted episode cost?

**I would proceed with WorkFactory as a methodological reference, GraphForge/WorkGenesis for evidence and task auditing, AgentGym as a candidate interaction framework, and OR plus state-based verification as the correctness foundation.** The immediate priority is proving that this combination produces trustworthy tasks and trustworthy scores before deciding how far to scale.
