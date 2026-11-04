import tempfile
import unittest
from pathlib import Path
from learning_lane import LearningLane, SQLiteLearningStore, ContractError

KGF = Path(__file__).with_name('LearningLane.kgf')
CANDIDATE = {'pattern':'how to grow tomatoes','W':0.8,'C':0.9,'R':0.7,'G':0.05,'S':0.504}

class TestLearningLane(unittest.TestCase):
    def test_durable_replay_and_gate(self):
        # ignore_cleanup_errors: the lane's _db() returns an unclosed connection,
        # which keeps the sqlite file open and makes Windows tempdir cleanup fail.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            path = Path(temp)/'learning.sqlite'
            lane = LearningLane(KGF, SQLiteLearningStore(path))
            proposal = lane.propose({'learning':[CANDIDATE]}, proposal_id='p1', principal='u1', workspace='w1')
            with self.assertRaises(PermissionError):
                lane.commit(proposal, admission='DATA_ONLY', sek_authorized=True, chen_verified=True, xul_closed=True)
            self.assertEqual(lane.store.projection(), {})
            gate = dict(admission='ADMITTED', sek_authorized=True, chen_verified=True, xul_closed=True)
            first = lane.commit(proposal, **gate)
            self.assertTrue(first['inserted'])
            self.assertFalse(lane.commit(proposal, **gate)['inserted'])
            restarted = LearningLane(KGF, SQLiteLearningStore(path))
            self.assertTrue(restarted.store.has(first['key']))
            self.assertEqual(restarted.store.projection(), {'how to grow tomatoes':0.05})
            changed = restarted.propose({'learning':[dict(CANDIDATE,G=0.1)]}, proposal_id='p1', principal='u1', workspace='w1')
            with self.assertRaises(ContractError):
                restarted.commit(changed, **gate)

if __name__ == '__main__':
    unittest.main()
