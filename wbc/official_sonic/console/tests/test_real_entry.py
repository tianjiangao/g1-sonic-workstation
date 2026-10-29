import unittest
from unittest.mock import Mock,patch
from official_sonic.console.app import Console
from official_sonic.console.backend import Config
from official_sonic.run_real_teleop import body_command

class RealEntryTests(unittest.TestCase):
    def test_v11_encoder_decoder_and_observations_are_selected_together(self):
        remote=body_command(Config(),'v11-test')[-1]
        for name in ['model_decoder.onnx','model_encoder.onnx','observation_config.yaml']:
            self.assertIn('policy/sonic_v1_1/'+name,remote)
            self.assertNotIn('policy/release/'+name,remote)
        self.assertNotIn('--motor-kp-scale',remote)
        self.assertNotIn('--motor-kd-scale',remote)
    def test_operator_decline_never_launches(self):
        app=Mock();app.jobs.running.return_value=False;app.config.return_value=Config()
        with patch('official_sonic.console.app.messagebox.askyesno',return_value=False):
            Console.start_real(app)
        app.start.assert_not_called()
    def test_operator_confirmation_starts_fixed_supervised_entry(self):
        app=Mock();app.jobs.running.return_value=False;app.config.return_value=Config()
        with patch('official_sonic.console.app.messagebox.askyesno',return_value=True):
            Console.start_real(app)
        app.start.assert_called_once_with('real')
    def test_only_original_sonic_binary_and_configured_host_are_selected(self):
        c=Config();args=body_command(c,'session-test');remote=args[-1]
        self.assertIn('exec ./target/release/g1_deploy_onnx_ref ',remote)
        self.assertNotIn('g1_deploy_real_trial',remote);self.assertNotIn('g1_deploy_sim',remote)
        self.assertIn('--zmq-host 192.168.123.99',remote)

if __name__=='__main__':unittest.main()

class ChildLogRelayTests(unittest.TestCase):
    def test_child_progress_and_error_are_visible_once(self):
        from official_sonic.run_real_teleop import ChildLogRelay
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from contextlib import redirect_stdout
        import io
        with TemporaryDirectory() as directory:
            run=Path(directory);relay=ChildLogRelay(run);out=io.StringIO()
            with redirect_stdout(out):
                relay.poll()
                log=run/'official-controller.log';log.write_text('Loading\n')
                relay.poll();relay.poll()
                with log.open('a') as f:f.write('Init Done\n')
                (run/'pico-streamer.log').write_text('Invalid triggers\n')
                relay.poll()
            self.assertEqual(out.getvalue().count('Loading'),1)
            self.assertEqual(out.getvalue().count('Init Done'),1)
            self.assertIn('Invalid triggers',out.getvalue())

class ChildHealthTests(unittest.TestCase):
    def test_gripper_failure_is_reported_once_without_stopping_body(self):
        from official_sonic.run_real_teleop import check_child_health
        reported=set();hand=Mock();hand.poll.return_value=1
        body=Mock();body.poll.return_value=None
        children=[('dex1-mapping',hand),('official-controller',body)]
        self.assertEqual(check_child_health(children,reported),[('dex1-mapping',1)])
        self.assertEqual(check_child_health(children,reported),[])
        body.terminate.assert_not_called()
    def test_tracking_loss_still_stops_body_session(self):
        from official_sonic.run_real_teleop import check_child_health
        pico=Mock();pico.poll.return_value=1
        with self.assertRaises(RuntimeError):check_child_health([('pico-streamer',pico)],set())

class NormalStopTests(unittest.TestCase):
    def test_normal_pico_stop_is_not_reported_as_gripper_failure(self):
        from official_sonic.run_real_teleop import check_child_health,NormalSessionEnd
        hand=Mock();hand.poll.return_value=1
        pico=Mock();pico.poll.return_value=0
        with self.assertRaises(NormalSessionEnd):check_child_health([('dex1-mapping',hand),('pico-streamer',pico)],set())
    def test_body_normal_exit_is_normal_session_end(self):
        from official_sonic.run_real_teleop import check_child_health,NormalSessionEnd
        body=Mock();body.poll.return_value=0
        with self.assertRaises(NormalSessionEnd):check_child_health([('official-controller',body)],set())
