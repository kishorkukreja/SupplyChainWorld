import unittest
from collections import Counter
from unittest.mock import patch
from supplychainworld.generation import (
    generate_candidate, generate_population, GenerationRejected, VARIANTS)
from supplychainworld.lineage import overlap_report, Assignment
from supplychainworld.verification import verify


class GenerationTests(unittest.TestCase):
    def test_repeatability_and_private_boundary(self):
        a = generate_candidate(41, 'lin-a', 'train', variant='moq', outcome='award')
        b = generate_candidate(41, 'lin-a', 'train', variant='moq', outcome='award')
        self.assertEqual(a.public_bundle(), b.public_bundle())
        self.assertEqual(a.private.reference, b.private.reference)
        public = a.public_bundle()
        self.assertNotIn('private', public)
        self.assertNotIn('expected_outcome', public['task'])
        self.assertNotIn('lineage', public['task'])
        self.assertNotIn('reference', str(public))

    def test_every_variant_and_outcome_independently_checked(self):
        for variant in VARIANTS:
            for outcome in ('award', 'clarification', 'infeasible'):
                with self.subTest(variant=variant, outcome=outcome):
                    c = generate_candidate(21, 'lineage-a', 'train', variant=variant, outcome=outcome)
                    self.assertTrue(verify(c.world, c.private.reference.submission(), outcome).accepted)
                    self.assertEqual(c.private.provenance['intended_outcome'], outcome)

    def test_excess_is_required_and_budget_is_binding(self):
        c = generate_candidate(3, 'lineage-a', 'train', variant='excess', outcome='award')
        allocations = c.private.reference.allocations
        for item in c.world.items:
            self.assertEqual(sum(a['quantity'] for a in allocations if a['item_id'] == item.item_id), item.demand + 1)
        b = generate_candidate(3, 'lineage-a', 'train', variant='budget', outcome='award')
        self.assertEqual(b.world.constraints.budget, b.private.reference.total_cost)

    def test_smoke_population_is_split_clean_and_complete(self):
        batch = generate_population(100)
        self.assertEqual(len(batch.candidates), 100)
        self.assertEqual(batch.attempted, 100)
        self.assertEqual(batch.rejection_counts, {})
        self.assertEqual(Counter(c.task.split for c in batch.candidates), {'train': 60, 'development': 20, 'evaluation': 20})
        self.assertEqual({c.task.expected_outcome for c in batch.candidates}, {'award', 'clarification', 'infeasible'})
        self.assertFalse(overlap_report([(c.task, c.world) for c in batch.candidates]))

    def test_bounded_rejections_are_counted(self):
        with patch('supplychainworld.generation.generate_candidate', side_effect=GenerationRejected('reference_timeout')):
            batch = generate_population(2, max_attempts_per_candidate=2)
        self.assertEqual(batch.attempted, 4)
        self.assertEqual(batch.rejection_counts, {'reference_timeout': 4})
        self.assertFalse(batch.candidates)

    def test_invalid_options_fail_explicitly(self):
        with self.assertRaises(ValueError):
            generate_candidate(1, 'lin-a', 'train', variant='fx')
        with self.assertRaises(ValueError):
            generate_population(-1)

    def test_forged_cross_split_ancestry_and_eval_public_bundle_rejected(self):
        supplied = {s: Assignment('lin-' + s, s, 'shared-template', 'source-' + s, ())
                    for s in ('train', 'development', 'evaluation')}
        with self.assertRaises(ValueError):
            generate_population(1, lineage_assignments=supplied)
        c = generate_candidate(2, 'lin-eval', 'evaluation', outcome='award')
        with self.assertRaises(ValueError):
            c.public_bundle()
