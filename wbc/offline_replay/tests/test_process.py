import json,os,time,unittest,urllib.request
from pathlib import Path
import numpy as np
from offline_replay.core import fingerprints
from offline_replay.launcher import launch
from offline_replay.tests.test_core import REAL

def get(url):
    with urllib.request.urlopen(url,timeout=10) as r:return json.load(r)
class ProcessTests(unittest.TestCase):
    def test_measured_frame_maps_body_and_dex1_and_exit_keeps_raw_and_ui(self):
        before=fingerprints(REAL);ui=[]
        for p in Path('/proc').glob('[0-9]*'):
            try:
                if b'official_sonic/console/app.py' in (p/'cmdline').read_bytes():ui.append(p)
            except OSError:pass
        h=launch(REAL)
        try:
            ready=h.wait_ready();meta=get(ready['url']+'meta');f=get(ready['url']+'frame?i=10&source=actual')
            self.assertEqual(meta['forbidden_imports_loaded'],[]);self.assertEqual(f['actuators'],0);self.assertEqual(f['physics_time'],0.)
            np.testing.assert_allclose(np.asarray(f['qpos'])[meta['body_qpos_addresses']],f['actual'])
            for name,position in f['gripper_mapping']['joints'].items():self.assertAlmostEqual(f['qpos'][meta['finger_qpos_addresses'][name]],position)
            self.assertEqual(f['index'],10);self.assertAlmostEqual(f['time_s'],meta['times'][10])
            self.assertNotIn(int(ready['url'].split(':')[2].split('/')[0]),(5555,5556,5557))
        finally:h.stop()
        final=json.loads(h.ready.with_suffix('.final.json').read_text());self.assertTrue(final['raw_unchanged']);self.assertEqual(fingerprints(REAL),before)
        for p in ui:self.assertTrue(p.exists(),'Workstation process disappeared during viewer exit')
    def test_viewer_crash_is_independent_and_does_not_change_raw(self):
        before=fingerprints(REAL);h=launch(REAL);h.wait_ready()
        h.process.kill();h.process.wait(timeout=5)
        self.assertNotEqual(h.process.returncode,0);self.assertEqual(fingerprints(REAL),before)
