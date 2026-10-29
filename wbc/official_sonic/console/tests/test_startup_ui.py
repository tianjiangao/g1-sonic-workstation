import importlib.util,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,Mock
try:
    import tkinter as tk
    AVAILABLE=bool(os.environ.get('DISPLAY')) and importlib.util.find_spec('PIL') is not None
except ImportError:AVAILABLE=False

@unittest.skipUnless(AVAILABLE,'Needs system Tk/PIL/display; no robot access')
class StartupUITests(unittest.TestCase):
    def test_live_job_phase_is_rendered_without_loading_or_starting_controller(self):
        from official_sonic.console.app import Console
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            (base/'startup-status.json').write_text(json.dumps({'pid':123,'time_epoch':time.time(),'phase':'WAIT_ENABLE','note':'ENGINEERING_TEST_ONLY','alert':''}))
            root=tk.Tk();fake=Mock();fake.poll.return_value=0
            try:
                with patch('official_sonic.console.app.BASE',base),patch('official_sonic.console.app.subprocess.Popen',return_value=fake),patch.object(Console,'check_ssh'),patch('official_sonic.console.app.JobManager.snapshot',return_value={'running':True,'name':'real','pid':123,'log':None,'returncode':None}):
                    app=Console(root);root.update_idletasks()
                    self.assertIn('WAIT_ENABLE',app.startup_note.get())
                    self.assertIn('ENGINEERING_TEST_ONLY',app.startup_note.get())
                    (base/'startup-status.json').write_text(json.dumps({'pid':123,'time_epoch':time.time(),'phase':'THERMAL_RISK','note':'诊断提示','alert':'右踝快速升温'}))
                    app.poll();self.assertIn('右踝快速升温',app.startup_note.get())
                    self.assertEqual(str(app.startup_label.cget('foreground')),'#b42318')
            finally:root.destroy()
