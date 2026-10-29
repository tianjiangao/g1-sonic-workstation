import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('capture_core',Path(__file__).parents[1]/'core.py')
core=importlib.util.module_from_spec(spec) if spec else None
if spec and spec.loader and Path(spec.origin).exists(): spec.loader.exec_module(core)
else: core=None


def sample():
    data={'g1_debug':{'body_q':list(range(29)),'last_action':[.1]*29},
          'manager_state':{'stream_mode':[1]},'robot_config':{'test':True},
          'dex1_left_state':{'q':1.,'dq':.1,'tau_est':.2},
          'dex1_right_state':{'q':2.,'dq':.2,'tau_est':.3},
          'dex1_left_cmd':{'q':3.},'dex1_right_cmd':{'q':4.},
          'camera_head':{'path':'images/head.jpg','shape':[480,1280,3]},
          'camera_left':{'path':'images/left.jpg','shape':[480,640,3]},
          'camera_right':{'path':'images/right.jpg','shape':[480,640,3]}}
    return {k:{'data':v,'mono_ns':1_000_000_000,'epoch_ns':1_000_000_000} for k,v in data.items()}

class ContractTests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(core,'capture implementation missing')
    def test_fresh_complete_inputs_preserve_physical_dex1_sides(self):
        frame=core.make_frame(sample(),1_100_000_000)
        self.assertEqual(frame['observation.dex1'],[1.,2.])
        self.assertEqual(frame['action.dex1'],[3.,4.])
        self.assertEqual(frame['observation.body'],list(range(29)))
    def test_stale_or_missing_side_cannot_be_filled_with_zero(self):
        for mode in ('missing','stale'):
            s=sample()
            if mode=='missing':del s['dex1_right_state']
            else:s['dex1_right_state']['mono_ns']=500_000_000
            with self.assertRaises(ValueError):core.make_frame(s,1_100_000_000)
    def test_rejects_nonfinite_or_wrong_dimension_body(self):
        for value in ([0.]*28,[float('nan')]*29):
            s=sample();s['g1_debug']['data']['body_q']=value
            with self.assertRaises(ValueError):core.make_frame(s,1_100_000_000)
    def test_image_stale_even_when_other_sources_are_fresh(self):
        s=sample();s['camera_head']['mono_ns']=100_000_000
        with self.assertRaises(ValueError):core.make_frame(s,1_100_000_000)
    def test_episode_retains_fault_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            ep=core.Episode(Path(d)/'episode');ep.append(core.make_frame(sample(),1_100_000_000));ep.close('source timeout')
            import json
            m=json.loads((Path(d)/'episode/episode.json').read_text())
            self.assertFalse(m['complete']);self.assertEqual(m['frames'],1)
            with self.assertRaises(FileExistsError):core.Episode(Path(d)/'episode')
    def test_quit_is_partial_and_normal_stop_is_complete(self):
        with tempfile.TemporaryDirectory() as d:
            import json
            for name,reason,expected in [('a','operator_stop',True),('b','process_exit',False)]:
                ep=core.Episode(Path(d)/name);ep.append(core.make_frame(sample(),1_100_000_000));ep.close(reason)
                self.assertEqual(json.loads((Path(d)/name/'episode.json').read_text())['complete'],expected)
    def test_schema_uses_two_dex1_values_and_preserves_stereo(self):
        ft,md=core.schema()
        self.assertEqual(ft['observation.dex1']['shape'],(2,))
        self.assertEqual(ft['observation.images.ego_view']['shape'],(480,1280,3))
        self.assertEqual(md['action']['dex1']['original_key'],'action.dex1')

if __name__=='__main__':unittest.main()
