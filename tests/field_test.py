import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "field"))
from main import parse_world, parse_bodies, parse_constraints
from pi_types import PiEvent
from pi_kernel import PiKernel

class FieldTest(unittest.TestCase):
    def test_typed_impulse_and_hash_lineage(self):
        bundle = {"%pi": {"world": {"gravity": [0, 0, 0]}, "bodies": [{"id": "one"}]}}
        def make():
            return PiKernel(parse_world(bundle), parse_bodies(bundle), parse_constraints(bundle), {})
        kernel = make()
        kernel.enqueue_event(PiEvent(type="impulse", target="one", payload={"impulse": [0, 2, 0]}))
        first = kernel.tick_once()
        second = kernel.tick_once()
        self.assertEqual(first.prev_hash, "0" * 64)
        self.assertEqual(second.prev_hash, first.tick_hash)
        self.assertGreater(first.projection.bodies["one"]["position"][1], 0)
        replay = make()
        replay.enqueue_event(PiEvent(type="impulse", target="one", payload={"impulse": [0, 2, 0]}))
        self.assertEqual(replay.tick_once().tick_hash, first.tick_hash)

if __name__ == "__main__":
    unittest.main()
