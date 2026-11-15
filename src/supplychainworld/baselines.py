"""S01 engineering baselines using only the environment's visible observation."""
from dataclasses import dataclass
from typing import Literal

from .dynamic import OperationalWorld

Policy = Literal['maintain', 'expedite', 'alternate']


@dataclass(frozen=True)
class BaselineResult:
    policy: str
    observations: list[dict]
    actions: list[dict]
    history: list[dict]
    scorecard: dict


def run_baseline(world: OperationalWorld, policy: Policy) -> BaselineResult:
    """Act after a visible notice and produce the largest currently feasible lot.

    This function is a scripted policy, not an LLM or proof of optimality. It
    receives no fixture answer key and never inspects hidden scenario configuration.
    """
    if policy not in ('maintain', 'expedite', 'alternate'):
        raise ValueError('unknown baseline policy')
    world.reset()
    observations, actions = [], []
    while True:
        obs = world.observation()
        observations.append(obs)
        state, rules = obs['state'], obs['rules']
        if state['phase'] == 'complete':
            break
        if state['notices'] and state['recovery'] is None:
            result = world.choose_recovery(policy)
            actions.append({'day': state['day'], 'kind': 'recovery', 'arguments': {'choice': policy}, 'result': result})
            if not result['accepted']:
                raise ValueError('baseline recovery was rejected: ' + result['reason'])
        quantity = min(rules['capacity'], state['component_on_hand'], rules['required'] - state['produced_total'])
        result = world.release_production(quantity)
        actions.append({'day': state['day'], 'kind': 'release', 'arguments': {'quantity': quantity}, 'result': result})
        if not result['accepted']:
            raise ValueError('baseline production was rejected: ' + result['reason'])
        world.close_day()
        actions.append({'day': state['day'], 'kind': 'close_day', 'arguments': {}, 'result': {'accepted': True}})
    return BaselineResult(policy, observations, actions, world.history(), world.scorecard())
