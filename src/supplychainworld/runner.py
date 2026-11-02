"""Provider-neutral observable runner. No provider SDK or credentials required."""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from time import monotonic
from typing import Any, Protocol

from .schemas import Action, ActionResult, Trajectory, World
from .solvers import solve_reference


def redact(value):
    """Remove credential-bearing fields before recording configuration."""
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if any(x in k.lower() for x in
                ('secret', 'token', 'password', 'api_key', 'authorization')) else redact(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


@dataclass(frozen=True)
class RunnerConfig:
    model_id: str = 'offline-visible-optimizer'
    max_actions: int = 12
    timeout_seconds: float = 30.0
    prompt: str = 'Use only visible records; submit a supported procurement recommendation.'
    memory_policy: str = 'episode_only_full_observable_history'
    retry_limit: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        import math
        if type(self.max_actions) is not int or self.max_actions < 0:
            raise ValueError('max_actions must be a nonnegative integer')
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds < 0:
            raise ValueError('timeout_seconds must be finite and nonnegative')
        if self.retry_limit != 0:
            raise ValueError('only the fixed no-retry policy is supported')


@dataclass(frozen=True)
class Decision:
    tool_name: str
    arguments: dict = field(default_factory=dict)


class Adapter(Protocol):
    def next_action(self, observation: dict, history: list[dict]) -> Decision: ...


@dataclass
class RunnerResult:
    task_id: str
    seed: int
    termination_reason: str
    manifest: dict
    observations: list[dict]
    actions: list[Action]
    results: list[ActionResult]
    trajectory: Trajectory | None = None
    error: str | None = None


def run_episode(env, adapter: Adapter, config: RunnerConfig | None = None, *,
                run_id: str = 'run', seed: int = 0) -> RunnerResult:
    config = config or RunnerConfig()
    initial = env.observe()
    observation = env.reset(initial['task_id'], seed)
    manifest = redact(asdict(config))
    manifest.update({'runner_version': '1.0', 'provider': 'unavailable',
                     'cost_ceiling': '0', 'adapter_profile': getattr(adapter, 'profile', 'custom'),
                     'seed': seed})
    out = RunnerResult(observation['task_id'], seed, 'tool_limit', manifest,
                       [deepcopy(observation)], [], [])
    started = monotonic()
    for index in range(config.max_actions):
        if monotonic() - started >= config.timeout_seconds:
            out.termination_reason = 'timeout'
            break
        try:
            history = [{'action': a.model_dump(mode='json'), 'result': r.model_dump(mode='json')}
                       for a, r in zip(out.actions, out.results)]
            decision = adapter.next_action(deepcopy(observation), deepcopy(history))
            if monotonic() - started >= config.timeout_seconds:
                out.termination_reason = 'timeout'
                break
            action = Action(tool_name=decision.tool_name, arguments=decision.arguments,
                            request_id=f'r{index}', state_version=observation['state_version'])
            out.actions.append(action.model_copy(deep=True))
            try:
                result = env.step(action)
            except Exception:
                from .schemas import TypedError
                result = ActionResult(request_id=action.request_id, state_version=observation['state_version'],
                                      error=TypedError(code='infrastructure_error', message='Environment call failed'))
                out.results.append(result)
                out.termination_reason = 'infrastructure_error'
                break
            out.results.append(result.model_copy(deep=True))
            observation = env.observe()
            out.observations.append(deepcopy(observation))
            if observation['terminated']:
                out.termination_reason = 'submitted'
                out.trajectory = Trajectory(run_id=run_id, task_id=out.task_id, model_id=config.model_id,
                    configuration=manifest, observations=out.observations, actions=out.actions,
                    results=out.results, final_submission=env.submission, termination_reason='submitted',
                    artifact_hashes=initial['artifacts'], usage={'actions': len(out.actions)}, cost='0')
                break
        except Exception:
            # Raw provider exceptions may contain credentials or private request bodies.
            out.termination_reason = 'adapter_error'
            out.error = 'Adapter decision failed; sensitive exception details omitted'
            break
    return out


def replay_run(env, result: RunnerResult) -> bool:
    observation = env.reset(result.task_id, result.seed)
    if observation != result.observations[0]:
        raise ValueError('initial observation diverged')
    if len(result.actions) != len(result.results) or len(result.observations) != len(result.actions) + 1:
        raise ValueError('unmatched action/result')
    for index, (action, expected) in enumerate(zip(result.actions, result.results)):
        actual = env.step(action)
        if actual.model_dump(mode='json') != expected.model_dump(mode='json'):
            raise ValueError('action result diverged')
        if index + 1 >= len(result.observations) or env.observe() != result.observations[index + 1]:
            raise ValueError('observation diverged')
    if result.trajectory is not None:
        t = result.trajectory
        if (result.termination_reason != 'submitted' or t.termination_reason != 'submitted'
                or t.task_id != result.task_id or t.configuration != result.manifest
                or t.actions != result.actions or t.results != result.results
                or t.observations != result.observations
                or t.artifact_hashes != result.observations[0]['artifacts']
                or t.final_submission.model_dump(mode='json') != env.submission):
            raise ValueError('trajectory diverged from replay')
    elif result.termination_reason == 'submitted':
        raise ValueError('submitted run requires trajectory')
    return True


class OfflineVisibleAgent:
    """Optimization baseline reconstructed only from successful visible reads."""
    profile = 'visible-records-exhaustive-optimizer-v1'

    def next_action(self, observation, history):
        records = {}
        for event in history:
            response = event['result']
            if response.get('observation') and 'records' in response['observation']:
                records[event['action']['tool_name']] = response['observation']['records']
        for name in ('requirements', 'inventory', 'suppliers', 'quotes', 'policy'):
            if name not in records:
                if name not in observation['tools']:
                    raise ValueError('required visible read unavailable')
                return Decision(name)
        policy = records['policy']
        world = World(world_id='visible', seed=0, currency=policy['currency'],
            calendar=policy['calendar'], as_of=policy['as_of'], items=records['requirements'],
            stock=records['inventory']['stock'], inbound=records['inventory']['inbound'],
            suppliers=records['suppliers'], quotes=records['quotes'],
            constraints=policy['constraints'], visibility={})
        solved = solve_reference(world)
        submission = solved.submission().model_dump(mode='json')
        if submission['kind'] == 'clarification' and not any(
            e['action']['tool_name'] == 'request_clarification' for e in history):
            return Decision('request_clarification', {'field': submission['field'],
                            'reason': 'Visible commercial term is missing'})
        return Decision('submit_award' if submission['kind'] == 'award' else 'submit_exception', submission)


def result_hash(result: RunnerResult) -> str:
    payload = {'manifest': result.manifest, 'observations': result.observations,
               'actions': [a.model_dump(mode='json') for a in result.actions],
               'results': [r.model_dump(mode='json') for r in result.results],
               'termination_reason': result.termination_reason}
    return sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
