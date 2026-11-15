import unittest
from test_environment import environment
from supplychainworld.runner import (Decision, OfflineVisibleAgent, RunnerConfig,
                                     replay_run, run_episode, result_hash)
from supplychainworld.verification import verify


class RunnerTests(unittest.TestCase):
    def test_all_reference_cases_observable_replay(self):
        for i in range(1, 11):
            with self.subTest(case=i):
                env, fixture = environment(f'ref-{i:02}')
                result = run_episode(env, OfflineVisibleAgent())
                self.assertEqual(result.termination_reason, 'submitted')
                self.assertTrue(replay_run(env, result))
                self.assertEqual(len(result.observations), len(result.actions) + 1)
                self.assertIsNotNone(result.trajectory)
                self.assertEqual(len(result_hash(result)), 64)
                from copy import deepcopy
                tampered = deepcopy(result)
                tampered.observations.append({})
                with self.assertRaises(ValueError):
                    replay_run(env, tampered)
                tampered = deepcopy(result)
                tampered.trajectory.final_submission.evidence = ['tampered']
                with self.assertRaises(ValueError):
                    replay_run(env, tampered)
                self.assertEqual(verify(env._initial_world, result.trajectory.final_submission, env._task.expected_outcome).accepted, True)

    def test_limits_errors_and_redaction(self):
        env, _ = environment()
        result = run_episode(env, OfflineVisibleAgent(), RunnerConfig(max_actions=1,
                             metadata={'api_key': 'sensitive'}))
        self.assertEqual(result.termination_reason, 'tool_limit')
        self.assertIsNone(result.trajectory)
        self.assertEqual(result.manifest['metadata']['api_key'], '[REDACTED]')
        self.assertTrue(replay_run(env, result))
        self.assertEqual(run_episode(env, OfflineVisibleAgent(), RunnerConfig(timeout_seconds=0)).termination_reason, 'timeout')

        class Broken:
            def next_action(self, observation, history):
                raise RuntimeError('secret credential')
        result = run_episode(env, Broken())
        self.assertEqual(result.termination_reason, 'adapter_error')
        self.assertNotIn('secret credential', result.error)

    def test_typed_error_captured_and_copies(self):
        env, _ = environment()
        class Invalid:
            def next_action(self, observation, history):
                self.assert_visible(observation, history)
                observation['request'] = 'tampered'
                return Decision('quotes', {'invalid': True})
            def assert_visible(self, observation, history):
                assert 'expected_outcome' not in observation
                assert 'world' not in observation
        result = run_episode(env, Invalid(), RunnerConfig(max_actions=2))
        self.assertEqual([r.error.code for r in result.results], ['invalid_arguments'] * 2)
        self.assertTrue(replay_run(env, result))
        result.observations[0]['request'] = 'tamper'
        with self.assertRaises(ValueError):
            replay_run(env, result)
