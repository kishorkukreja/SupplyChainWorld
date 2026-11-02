# Issue #5 implementation plan

Scope: specification §§3, 6, 7; prerequisites #2 and #3. Implementation waits for the domain and foundation agents' explicit shared JSON/schema agreement. No alternate schema will be introduced.

1. Implement an independent exact reference search over bounded integral award domains, with Decimal landed-cost accounting, supplier fixed fees once, eligibility, net demand, excess, budget and supplier landed-spend concentration constraints.
2. Bound execution by elapsed time and enumerated states. Only exhaustive completion may establish infeasibility or optimality. Interrupted search reports timeout, preserving any incumbent and a conservative zero lower bound; missing commercial information reports clarification.
3. Implement a conventional cost-ordered greedy baseline with independent feasibility checking; inability to construct an award must not imply infeasibility.
4. Validate all ten synthetic hand-worked references, valid objective ties and timeout behavior. Compare solver awards through the independently maintained checker when its API is available.
5. Record exact commands, results and scalability limitations in issue-5-results.md. No paid services, git operations or publication.

Decision: use bounded exhaustive search for the deliberately small reference cases, avoiding optional commercial/external optimizer dependencies. This is not a scalable production optimizer. Per-variable domains will be generated lazily and search limits checked during traversal.
