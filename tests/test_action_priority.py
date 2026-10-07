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


class NativeCrossbowRoutingTests(unittest.TestCase):
    def states(self):
        from types import SimpleNamespace as N
        idle=N(conditions=[N(next_state_id=n) for n in (9000,9001,9002,9003,225)])
        return {0:idle,65:N(conditions=[N(next_state_id=n) for n in (94,67,0)]),
                67:N(conditions=[N(next_state_id=n) for n in (61,68,0)]),68:N(conditions=[N(next_state_id=n) for n in (108,0)])}

    def test_requests_lead_every_native_crossbow_state(self):
        from dsr_mw2.action_priority import route_native_crossbow
        states=self.states()
        self.assertTrue(route_native_crossbow(states))
        for number,rest in ((65,[94,67,0]),(67,[61,68,0]),(68,[108,0])):
            self.assertEqual([c.next_state_id for c in states[number].conditions],[9000,9001,9002,*rest])
        self.assertIsNot(states[65].conditions[0],states[0].conditions[0])
        self.assertFalse(route_native_crossbow(states))

    def test_unexpected_idle_dispatch_changes_nothing(self):
        from dsr_mw2.action_priority import route_native_crossbow
        states=self.states();states[0].conditions[0].next_state_id=225
        with self.assertRaises(ValueError):route_native_crossbow(states)
        self.assertEqual([c.next_state_id for c in states[65].conditions],[94,67,0])
