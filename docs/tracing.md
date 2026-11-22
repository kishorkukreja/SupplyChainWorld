# Langfuse tracing (version 1)

Status: code and offline tests only. No trace has been sent to a live Langfuse project yet. Tracing is OFF by default.

## What it does

`src/supplychainworld/tracing.py` turns one finished S01 episode (the `raw` record from `eval19_v3.run_s01_episode` and its `grade`
from `grade_s01`) into a plan, then sends it to Langfuse. It runs after the episode and touches nothing inside the world, runner,
checker or adapter, so it cannot change a run, a verdict or a replay. The saved run files stay the record of truth.

| Langfuse | What we send |
|---|---|
| Trace | One per episode, named `run-s01-episode`. The id comes from the recorded run, so exporting twice does not duplicate. |
| Session | The run label (for example one eval run), so all episodes of a run group together. |
| `agent` observation | The episode: fixture, horizon, initial observation, final status and checker facts. |
| `generation` | One per model call: model, the observation shown, the tool call chosen, tokens, cost, latency in metadata. |
| `tool` | One per tool call: arguments, accepted or refused, the reason and category, state changes and events. |
| Scores | One per checker fact (feasible, replay reproduced, leak-free, violations, invalid actions, each metric). Never blended. Metric scores say PROVISIONAL. |

## Turning it on

```
pip install -e ".[trace]"
export SCW_LANGFUSE=1
export LANGFUSE_PUBLIC_KEY=...   # set in the environment's secret settings, never in chat or the repo
export LANGFUSE_SECRET_KEY=...
export LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or the US region, or a self-hosted URL
```

```python
client = tracing.tracing_client()          # None unless all four are set, so off by default
tracing.trace_episode(raw, grade, client, run_label='eval19-3-run1', private_strings=[...])
```

`trace_episode` never raises: a Langfuse problem returns `{'exported': False, ...}` and the run is untouched. Self-hosting later
only means changing `LANGFUSE_BASE_URL`.

## Safety rules (tested)

- Keys are read only by the Langfuse SDK from the environment; this module checks they are set and never reads, prints or stores them.
- Only the agent-visible record is used. `raw['world']` is never read (a test makes any access fail).
- Secret-looking strings are replaced and credential-named keys dropped. A plan containing any string in `private_strings` is refused, not redacted.
- Sealed or private evaluation data must never be traced. Everything here is synthetic.

## Known limits

- Sent after the run, so Langfuse timestamps are export time. Real latency is in each generation's metadata.
- Each generation shows the observation of that step and the system prompt on the first step. The model's earlier exchanges (memory window of 8) are the preceding steps of the same trace.
- Model calls and tool calls are paired by order, which holds in the mocked runs. A run with extra model calls (nudges) would show fewer generations than tools.
- Not yet checked against a live Langfuse project, and the Langfuse best-practices audit of a real trace (fetch it back and audit) is still to do.
