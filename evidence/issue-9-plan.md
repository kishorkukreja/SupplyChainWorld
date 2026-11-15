# Issue 9 plan

Implement a provider-neutral, zero-cost offline runner (spec sections 5, 6, 8, 9 and 11). The adapter receives copies of the actual initial observation and recorded action results only; it never receives the environment, task, expected outcome or original world. The optimization baseline reconstructs inputs from five successful public reads and declares this profile explicitly.

Record every dispatched action and result, including errors, and preserve partial runs without inventing a final submission. Fix prompts, memory policy, retries and budgets in a manifest; redact secret-bearing configuration and exception text. Replay every result against a freshly reset environment. Verify successful trajectories with the independent checker and test failures, budgets, visibility, redaction and divergence. No paid calls, publication or git changes.
