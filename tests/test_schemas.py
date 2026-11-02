import copy
import unittest
from decimal import Decimal
from pydantic import ValidationError
from supplychainworld.schemas import World, ExportManifest, ActionResult, parse_submission


def sample_world():
    return dict(world_id='w1', seed=1, currency='USD', as_of='2026-11-02',
        items=[dict(item_id='part', demand=10, due_date='2026-11-10', excess_allowance=0)],
        stock=[], inbound=[], suppliers=[dict(supplier_id='s1', fixed_charge='2.00')],
        quotes=[dict(supplier_id='s1', item_id='part', unit_price='1.005', variable_freight='0',
          capacity=10, moq=0, multiple=1, qualified=True, valid_from='2026-11-01',
          valid_to='2026-11-03', arrival_date='2026-11-09')],
        constraints=dict(budget='100', concentration_limit='1'), visibility=dict(classification='public_synthetic'))

class SchemaTests(unittest.TestCase):
    def test_exact_money_and_json_roundtrip(self):
        world = World.model_validate(sample_world())
        self.assertEqual(world.quotes[0].unit_price, Decimal('1.005'))
        self.assertEqual(World.model_validate_json(world.model_dump_json()), world)

    def test_missing_commercial_term_is_representable(self):
        value = sample_world()
        value['quotes'][0]['unit_price'] = None
        self.assertIsNone(World.model_validate(value).quotes[0].unit_price)

    def test_invalid_worlds(self):
        mutations = [
            lambda w: w.update(schema_version='2.0'),
            lambda w: w.update(currency='EUR'),
            lambda w: w['items'][0].update(unit='kg'),
            lambda w: w['items'][0].update(demand=1.5),
            lambda w: w['items'][0].update(demand=True),
            lambda w: w['items'][0].update(due_date='2026-02-30'),
            lambda w: w['items'].append(copy.deepcopy(w['items'][0])),
            lambda w: w['quotes'][0].update(supplier_id='missing'),
            lambda w: w['quotes'][0].update(item_id='missing'),
            lambda w: w['quotes'][0].update(unit_price=1.2),
            lambda w: w['quotes'][0].update(unit_price='NaN'),
            lambda w: w['quotes'][0].update(unit_price='-1'),
            lambda w: w['quotes'][0].update(multiple=0),
            lambda w: w['quotes'][0].update(qualified='yes'),
            lambda w: w['quotes'][0].update(valid_to='2026-10-01'),
            lambda w: w['constraints'].update(concentration_limit='1.1'),
            lambda w: w.update(hidden_answer='secret'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                value = sample_world()
                mutate(value)
                with self.assertRaises(ValidationError):
                    World.model_validate(value)

    def test_submission_discrimination_and_duplicates(self):
        value = dict(kind='award', allocations=[dict(supplier_id='s1',item_id='part',quantity=10)], claimed_total_cost='12',evidence=[])
        self.assertEqual(parse_submission(value).allocations[0].quantity,10)
        value['allocations'] *= 2
        with self.assertRaises(ValidationError): parse_submission(value)
        with self.assertRaises(ValidationError): parse_submission(dict(kind='infeasible',evidence=[]))

    def test_result_exclusive_payload(self):
        with self.assertRaises(ValidationError):
            ActionResult(request_id='r1', state_version=0)

    def test_manifest_lineage_leakage(self):
        data = dict(dataset_version='v1', accepted_count=2,rejected_count=0,source_use_status='synthetic_public',filtering_reasons={},accepted=[
            dict(task_id='t1',lineage='l1',split='train',trajectory_hash='a'*64),
            dict(task_id='t2',lineage='l1',split='evaluation',trajectory_hash='b'*64)])
        with self.assertRaises(ValidationError): ExportManifest.model_validate(data)

if __name__ == '__main__': unittest.main()
