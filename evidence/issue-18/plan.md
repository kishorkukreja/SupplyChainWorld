# Issue #18 plan

## Objective

Let one real LLM act through the existing S01 operational tools (`ObservableRunner`) with the same observable information boundary as the scripted agents, with pinned configuration, budgets and honest telemetry.

## Decisions recorded (owner, via worker brief; stored in `config/llm_roster.json`)

- Provider: OpenRouter, OpenAI-compatible chat completions (`https://openrouter.ai/api/v1/chat/completions`).
- Spend: approved ceiling is USD 0.00. The adapter refuses a model unless its id ends in `:free` or OpenRouter pricing is verified as exactly `0` for prompt and completion. Ceiling is configurable (default 0) and enforced from provider-reported cost.
- Credential: `OPENROUTER_API_KEY` read from the environment only. In this sandbox a proxy injects the real key, so commands use the placeholder `proxy-injected`. Nothing prints, logs or commits a key; strings and `Authorization` keys are redacted from every stored record.
- Roles: `general_reasoning`, `code`, `multimedia` are `actor` slots. `decision_system1` was first unresolved (the requested `perplexity/pplx-decider-v1.3:free` does not exist on OpenRouter). The owner then named `respan/span-01-lite`: `kind: scorer`, status `configured`, verified $0 pricing but no `:free` suffix, modality `text->decisions`, empty `supported_parameters`, context 0. Scorers never act through the runner (the adapter rejects `role_kind != 'actor'`). Its request/response format is not documented in the public model endpoint or page, so connectivity for this slot is "not attempted, request format unverified".

## Design

- `src/supplychainworld/llm_adapter.py` (stdlib only). `LLMAgent` is an `agent(view)` callable for `ObservableRunner.run`; it builds prompts only from the runner view and returns tool calls that the runner validates and executes. It does not import the world, scenario, verifier or baselines (checked by a test).
- Runner tool definitions are translated to OpenAI tool schemas (static, no per-step values).
- Run manifest pins model, endpoint, system prompt, tool schemas, request parameters, memory policy (rolling window, no cross-episode memory), retry/timeout policy, call/token/context limits, spend rules, with a SHA-256.
- Handling: malformed arguments are forwarded unrepaired and rejected/audited by the runner; only the first tool call per reply runs; non-tool replies get a bounded nudge; HTTP 429/5xx/network errors retry with capped exponential backoff and Retry-After; 4xx, refusals and context limits stop the episode as an `agent_error`; call, token, cost and context limits stop as `agent_stopped`. No success or usage is ever filled in.
- Telemetry per model call: HTTP requests, retries, latency, provider usage (only if reported), finish reason, cost (0 only for confirmed free with usage; reported cost used when present; otherwise `unknown`).

## Scope

Additive: new module, config, tests, two scripts, evidence. No existing `src` behavior changed. Not a model evaluation.
