# Sarvam provider for the S01 run (adapter version 2)

Status: code and mocked tests only. No call has been made to Sarvam. `SARVAM_API_KEY` is read from the environment only.

## Decision this implements

Owner decision 2026-11-23: Sarvam gets its own adapter (cap first set at INR 1000, then raised to INR 10000 the same day). The $0 free-only rule stays for OpenRouter. Sarvam calls are paid, with one
hard cap of INR 10000 across all Sarvam models in a run. `llm_adapter.py` is not edited (the first diagnostic's manifest hashes it),
and it still refuses every non-free OpenRouter id (a test checks this).

**Proposed wording for CLAUDE.md (not applied; the owner decides):** replace "No paid model calls. Free-tier models only, with a $0
ceiling, through the existing adapter." with "OpenRouter: free-tier models only, $0 ceiling, through `llm_adapter`. Sarvam: paid,
through `sarvam_adapter` only, with a hard cap of INR 10000 per run, stated in the committed test plan before any call."

## How it works

- `SarvamConfig`: an `AdapterConfig` that accepts only models in a pinned price table: `sarvam-105b`, `glm5.3-flash`,
  `deepseekv4.1-flash-1017`. The cap must be above 0 and at most INR 10000.
- `SarvamTransport`: a base transport. Wrap it in `eval19.Guard` like the OpenRouter one, so request caps, throttle, leak scan and
  ledger are unchanged. It drops `parallel_tool_calls`, refuses any call whose worst-case price could pass the cap, prices each answer
  from reported tokens, writes the estimate into `usage.cost` so the agent's own budget check works, and stops for good on HTTP 402.
- `SarvamSpend`: the running total in INR, rebuilt from a ledger file so a restart cannot exceed the cap.
- `run_s01_episode`: the S01 v0.6 episode on a Sarvam model; grade it with `eval19_v3.grade_s01`. The manifest says provider sarvam,
  paid and capped, not free-only.

## Money rules

- Costs are ESTIMATES from a pinned table, PROVISIONAL: read from docs.sarvam.ai on 2026-11-23, listed without GST, so GST (18 percent)
  is added, and cached-input discounts are ignored. Re-read the pricing page before the run and update the table in a new commit.
- Worst case before every call: one token per request byte plus the full `max_tokens` output. Each call RESERVES its worst case
  atomically (so concurrent calls cannot both pass) and the reservation is written to the ledger before the request is sent. It is
  settled at the priced usage afterwards. A reservation that never settles (a crash or kill) stays counted at its worst case after a
  restart.
- Charged at the worst case, never at zero: missing or junk usage, a timeout, a 5xx, an unreadable 200. Not charged: an HTTP 4xx
  refusal (the provider rejected the request). Every retry is a new reservation.
- If a provider ever reports more tokens than the request allowed, that call is counted, every later call is refused, and the ledger
  records `provider_exceeded_limits`. The cap is exact only for a provider that respects `max_tokens`.

## Not yet checked (needs a live call, in a session that has the key)

- That Sarvam accepts the request shape (tools, `tool_choice`) and returns `usage` with prompt and completion tokens.
- Whether reasoning tokens appear in `completion_tokens` (the docs say they are billed as output).
- Sarvam's terms on training use of requests and outputs: not found in the docs read. Check before any teacher or training use.
