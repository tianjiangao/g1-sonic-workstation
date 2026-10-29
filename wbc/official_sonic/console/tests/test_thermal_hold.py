import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from official_sonic.console.backend import Config
from official_sonic import run_real_teleop as entry

class ThermalHoldTests(unittest.TestCase):
    def check_hold(self,record):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'hold.json';path.write_text(json.dumps(record))
            d={'controllers':[],'autostart':'inactive','dex1_pids':[1],'container_running':True}
            with patch.object(entry,'HEALTH_HOLD_PATH',path,create=True),patch.object(entry,'remote_action',return_value=d) as remote,patch.object(entry,'motion_handoff',return_value={}) as handoff,patch.object(entry,'body_dds_check',return_value={}):
                with self.assertRaisesRegex(RuntimeError,'热安全|健康记录'):
                    entry.preflight(Config())
                remote.assert_not_called();handoff.assert_not_called()
    def test_latched_heat_prevents_even_prepare_or_release(self):
        self.check_hold({'blocked':True,'reason':'Right Ankle Pitch 93C, 24.5Nm; unresolved','report':'engineering evidence'})
    def test_malformed_health_record_fails_closed(self):
        self.check_hold({'blocked':'false'})
