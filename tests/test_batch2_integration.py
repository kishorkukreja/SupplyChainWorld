"""Independent cross-module boundary and tamper regressions."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import unittest

from supplychainworld.environment import ProcurementEnvironment, TOOLS, render_artifacts
from supplychainworld.lineage import LineageRegistry, agent_task_view, training_export_allowed
from supplychainworld.runner import OfflineVisibleAgent, run_episode, replay_run
from supplychainworld.schemas import Task, World
from supplychainworld.verification import verify


def public_episode(split='train'):
    fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/reference_cases/ref-02.json').read_text())
    world = World.model_validate(fixture['world'])
    registry = LineageRegistry()
    assignment = registry.assign('integration-source', 'integration-template', split=split)
    task = Task(task_id='integration', world_id=world.world_id, lineage=assignment.lineage,
                split=split, request=fixture['request'], visible_artifacts=list(render_artifacts(world)),
                permitted_tools=TOOLS, expected_outcome='award')
    return world, task, registry, assignment


class Batch2Integration(unittest.TestCase):
    def test_visible_optimizer_replays_and_independent_checker_accepts(self):
        world, task, _, _ = public_episode()
        env = ProcurementEnvironment(world, task)
        run = run_episode(env, OfflineVisibleAgent(), seed=world.seed)
        self.assertEqual(run.termination_reason, 'submitted')
        self.assertTrue(replay_run(env, run))
        self.assertTrue(verify(world, env.submission).accepted)
        self.assertEqual([a.tool_name for a in run.actions[:5]], ['requirements','inventory','suppliers','quotes','policy'])
        for view in run.observations:
            self.assertNotIn('expected_outcome', view)
            self.assertNotIn('split', view)
            self.assertNotIn('lineage', view)

    def test_registry_rejects_forged_split(self):
        _, task, registry, assignment = public_episode()
        forged = replace(assignment, split='evaluation')
        task = task.model_copy(update={'split':'evaluation'})
        with self.assertRaises(ValueError):
            registry.verify(task, forged)

    def test_ancestor_cannot_cross_split_and_eval_cannot_export(self):
        registry = LineageRegistry()
        registry.assign('first', 'first-template', ['shared'], split='train')
        with self.assertRaises(ValueError):
            registry.assign('second', 'second-template', ['shared'], split='evaluation')
        _, task, _, _ = public_episode('evaluation')
        with self.assertRaises(ValueError):
            training_export_allowed(task)
        self.assertNotIn('expected_outcome', agent_task_view(task))

    def test_supplied_population_assignments_reject_shared_ancestor(self):
        from supplychainworld.generation import generate_population
        from supplychainworld.lineage import Assignment
        splits = ('train', 'development', 'evaluation')
        assignments = {s: Assignment('lineage-' + s, s, 'template-' + s,
                                    'source-' + s, ('shared-root',)) for s in splits}
        with self.assertRaises(ValueError):
            generate_population(count=0, lineage_assignments=assignments)

    def test_admission_rejects_injected_answer_and_eval_has_no_record(self):
        from supplychainworld.admission import admit
        world, task, _, _ = public_episode('evaluation')
        run = run_episode(ProcurementEnvironment(world, task), OfflineVisibleAgent(), seed=world.seed)
        clean = admit(world, task, run.trajectory, split_assignments={task.lineage: task.split})
        self.assertTrue(clean.accepted, clean.reasons)
        self.assertIsNone(clean.record)
        run.trajectory.observations[0]['expected_outcome'] = 'private-answer-sentinel'
        rejected = admit(world, task, run.trajectory, split_assignments={task.lineage: task.split})
        self.assertFalse(rejected.accepted)
        self.assertIsNone(rejected.record)

    def test_replay_rejects_extra_observation(self):
        world, task, _, _ = public_episode()
        env = ProcurementEnvironment(world, task)
        run = run_episode(env, OfflineVisibleAgent(), seed=world.seed)
        run.observations.append(deepcopy(run.observations[-1]))
        with self.assertRaises(ValueError):
            replay_run(env, run)

    def test_replay_rejects_changed_result(self):
        world, task, _, _ = public_episode()
        env = ProcurementEnvironment(world, task)
        run = run_episode(env, OfflineVisibleAgent(), seed=world.seed)
        run.results[0].observation['records'][0]['demand'] += 1
        with self.assertRaises(ValueError):
            replay_run(env, run)


if __name__ == '__main__':
    unittest.main(verbosity=2)
