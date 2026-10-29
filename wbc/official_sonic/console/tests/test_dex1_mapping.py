import math
import unittest
from official_sonic.dex1_mapping import map_triggers,InputGate

class MappingTests(unittest.TestCase):
    def test_left_and_right_are_independent_and_press_closes(self):
        self.assertEqual(map_triggers(0,0),(7.,7.))
        self.assertEqual(map_triggers(1,0),(5.,7.))
        self.assertEqual(map_triggers(0,1),(7.,5.))
        self.assertEqual(map_triggers(.25,.75),(6.5,5.5))
    def test_invalid_trigger_is_rejected(self):
        for value in [float('nan'),float('inf'),-.01,1.01,None,'1']:
            with self.subTest(value=value),self.assertRaises(ValueError):map_triggers(value,0)
    def test_first_light_press_closes_from_captured_starting_aperture(self):
        left,right=map_triggers(.2,0,openings=(2.8,2.4))
        self.assertLess((left-5.)/2.*5.4,2.8)
        self.assertAlmostEqual((right-5.)/2.*5.4,2.4)
        released=map_triggers(0,0,openings=(2.8,2.4))
        self.assertAlmostEqual((released[0]-5.)/2.*5.4,2.8)
    def test_gate_requires_active_mode_fresh_body_and_fresh_trigger(self):
        g=InputGate();g.update_manager(0,10)
        g.update_trigger({'sequence':1,'timestamp_monotonic':10,'left':0.,'right':0.},10)
        self.assertFalse(g.allowed(10.1));g.update_manager(1,10.1);self.assertTrue(g.allowed(10.1))
        self.assertFalse(g.allowed(10.3));g.update_manager(0,10.31)
        self.assertFalse(g.allowed(10.31))
    def test_replay_or_future_frame_does_not_refresh_deadline(self):
        g=InputGate();g.update_manager(1,20)
        g.update_trigger({'sequence':1,'timestamp_monotonic':20.,'left':0.,'right':0.},20)
        with self.assertRaises(ValueError):g.update_trigger({'sequence':1,'timestamp_monotonic':20.,'left':1.,'right':0.},20.1)
        with self.assertRaises(ValueError):g.update_trigger({'sequence':2,'timestamp_monotonic':21.,'left':1.,'right':0.},20.1)
        self.assertFalse(g.allowed(20.3))

if __name__=='__main__':unittest.main()

class TrialLimiterTests(unittest.TestCase):
    def test_close_stops_before_endpoint_and_slews_from_start(self):
        from official_sonic.dex1_mapping import TrialLimiter
        limit=TrialLimiter((2.8,2.4))
        result=limit.advance(map_triggers(1,0,openings=(2.8,2.4)),.02)
        self.assertAlmostEqual((result[0]-5)*2.7,2.79)
        self.assertAlmostEqual((result[1]-5)*2.7,2.4)
        for _ in range(800):result=limit.advance((5.,5.),.02)
        self.assertAlmostEqual((result[0]-5)*2.7,.15)
        self.assertAlmostEqual((result[1]-5)*2.7,.15)
    def test_already_closed_start_never_opens_itself(self):
        from official_sonic.dex1_mapping import TrialLimiter
        limit=TrialLimiter((.05,2.4))
        for _ in range(20):result=limit.advance((7.,7.),.02)
        self.assertAlmostEqual((result[0]-5)*2.7,.05)
        self.assertAlmostEqual((result[1]-5)*2.7,2.4)
    def test_stalled_iteration_does_not_allow_large_step(self):
        from official_sonic.dex1_mapping import TrialLimiter
        limit=TrialLimiter((2.8,2.4))
        result=limit.advance((5.,5.),10)
        self.assertAlmostEqual((result[0]-5)*2.7,2.775)

class FeedbackValidationTests(unittest.TestCase):
    def test_small_encoder_overshoot_is_not_a_command_limit_violation(self):
        from official_sonic.dex1_mapping import validate_feedback
        validate_feedback(-.02,-.1,.01)
    def test_nonfinite_feedback_remains_rejected(self):
        from official_sonic.dex1_mapping import validate_feedback
        for values in [(float('nan'),0,0),(0,float('inf'),0),(0,0,float('-inf'))]:
            with self.assertRaises(ValueError):validate_feedback(*values)

class FullOpeningTests(unittest.TestCase):
    def targets(self, openings=(2.8,2.4), **kwargs):
        from official_sonic import dex1_mapping as mapping
        self.assertTrue(hasattr(mapping,'TriggerTargets'), 'Full-opening target adapter is missing')
        return mapping.TriggerTargets(openings, **kwargs)
    def q(self, values):return tuple((x-5.)*2.7 for x in values)
    def test_startup_does_not_open_either_hand(self):
        t=self.targets();q=self.q(t.advance(0,0,(2.8,2.4)))
        self.assertAlmostEqual(q[0],2.8);self.assertAlmostEqual(q[1],2.4)
    def test_first_squeeze_closes_then_release_targets_full_open_only_on_that_side(self):
        t=self.targets();q=self.q(t.advance(.2,0,(2.8,2.4)))
        self.assertLess(q[0],2.8);self.assertAlmostEqual(q[1],2.4)
        q=self.q(t.advance(0,0,(2.1,2.4)))
        self.assertAlmostEqual(q[0],5.4);self.assertAlmostEqual(q[1],2.4)
        t.advance(0,.3,(3.,2.4));q=self.q(t.advance(0,0,(3.,1.7)))
        self.assertAlmostEqual(q[0],5.4);self.assertAlmostEqual(q[1],5.4)
    def test_squeeze_during_reopening_still_closes_from_actual_aperture(self):
        t=self.targets();t.advance(.8,0,(2.8,2.4));t.advance(0,0,(1.,2.4))
        q=self.q(t.advance(.2,0,(2.,2.4)))
        self.assertLess(q[0],2.)
    def test_released_trigger_noise_does_not_reclose_or_activate_other_hand(self):
        t=self.targets();t.advance(.2,0,(2.8,2.4));t.advance(0,0,(2.,2.4))
        q=self.q(t.advance(.08,.08,(3.,2.4)))
        self.assertAlmostEqual(q[0],5.4);self.assertAlmostEqual(q[1],2.4)
    def test_explicit_legacy_mode_retains_start_opening(self):
        t=self.targets(return_to_start=True);t.advance(.2,.2,(2.8,2.4))
        q=self.q(t.advance(0,0,(1.,1.)))
        self.assertAlmostEqual(q[0],2.8);self.assertAlmostEqual(q[1],2.4)
    def test_invalid_feedback_does_not_mutate_activation(self):
        t=self.targets()
        with self.assertRaises(ValueError):t.advance(1.,0,(float('nan'),2.4))
        q=self.q(t.advance(0,0,(2.8,2.4)))
        self.assertAlmostEqual(q[0],2.8);self.assertAlmostEqual(q[1],2.4)

class AutomaticOpeningTests(unittest.TestCase):
    def test_automatic_opening_ramps_both_sides_to_full_without_trigger_press(self):
        from official_sonic.dex1_mapping import TriggerTargets
        t=TriggerTargets((2.8,2.4),auto_open=True)
        q=tuple((x-5)*2.7 for x in t.advance(0,0,(2.8,2.4),dt=.02))
        self.assertAlmostEqual(q[0],2.81);self.assertAlmostEqual(q[1],2.41)
        for _ in range(800):values=t.advance(0,0,(q[0],q[1]),dt=.02);q=tuple((x-5)*2.7 for x in values)
        self.assertAlmostEqual(q[0],5.4);self.assertAlmostEqual(q[1],5.4)
    def test_press_during_auto_open_closes_from_actual_state(self):
        from official_sonic.dex1_mapping import TriggerTargets
        t=TriggerTargets((2.8,2.4),auto_open=True)
        q=tuple((x-5)*2.7 for x in t.advance(.2,0,(2.8,2.4),dt=.02))
        self.assertLess(q[0],2.8);self.assertAlmostEqual(q[1],2.41)
    def test_stalled_iteration_does_not_jump_open(self):
        from official_sonic.dex1_mapping import TriggerTargets
        t=TriggerTargets((2.8,2.4),auto_open=True)
        q=tuple((x-5)*2.7 for x in t.advance(0,0,(2.8,2.4),dt=100))
        self.assertAlmostEqual(q[0],2.825);self.assertAlmostEqual(q[1],2.425)
