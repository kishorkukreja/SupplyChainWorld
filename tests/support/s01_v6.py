"""S01 v0.6 adapter for the shared audit helpers (see `s01_versions.py`; that file is not edited).

`V6` is a `Version` like the others, so the same property, mutation and fuzz helpers run on it. Also holds the
generators and the helpers the v0.6 tests share.
"""
from hypothesis import strategies as st

from supplychainworld import agent_runner_v6 as r6, dynamic_v6 as d6, dynamic_verifier_v6 as vf6

from support.s01_versions import SCENARIO_STRATEGIES, Version, V5, _HID2, v3_scenarios

V6 = Version('v0.6', scenario_cls=d6.ScenarioV6, world_cls=d6.OperationalWorldV6, runner_cls=r6.ObservableRunnerV6,
             replay=r6.replay_v6, scripted=r6.scripted_policy_v6, policies=r6.POLICIES_V6, verify=vf6.verify_episode,
             fixtures_path='fixtures/dynamic/v0.6/scenarios.json', hidden_keys=_HID2,
             leaks=vf6.check_observations_for_leaks, multi_commit=True)
SCENARIOS_V6 = v3_scenarios().map(lambda pair: ({**pair[0], 'scenario_id': d6.opaque_label(pair[0])}, pair[1]))
SCENARIO_STRATEGIES['v0.6'] = SCENARIOS_V6
__all__ = ['V6', 'V5', 'SCENARIOS_V6', 'st']
