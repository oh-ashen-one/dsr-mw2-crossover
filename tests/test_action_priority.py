import unittest
from types import SimpleNamespace
from dsr_mw2.action_priority import prioritize_requests


class ActionPriorityTests(unittest.TestCase):
    def test_held_aim_does_not_swallow_single_frame_requests(self):
        conditions = [SimpleNamespace(next_state_id=n) for n in (9003,9000,9001,9002,225)]
        original = conditions[:]
        self.assertTrue(prioritize_requests(conditions))
        for request, destination in ((37,9000),(38,9001),(39,9002)):
            with self.subTest(request=request):
                # ESD takes the first true branch. Aim remains true throughout
                # a click/reload; the request is only true for this frame.
                true_destinations = {9003,destination}
                winner = next(c.next_state_id for c in conditions if c.next_state_id in true_destinations)
                self.assertEqual(winner,destination)
        self.assertEqual(next(c.next_state_id for c in conditions if c.next_state_id==9003),9003)
        self.assertIs(conditions[-1],original[-1])
        self.assertEqual({id(c) for c in conditions},{id(c) for c in original})
        self.assertFalse(prioritize_requests(conditions))

    def test_unrecognized_dispatch_is_preserved(self):
        conditions=[SimpleNamespace(next_state_id=n) for n in (9003,9000,225,9002)]
        before=conditions[:]
        with self.assertRaises(ValueError):prioritize_requests(conditions)
        self.assertEqual(conditions,before)
