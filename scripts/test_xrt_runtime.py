import unittest
from unittest.mock import patch
from gear_sonic.utils.teleop.xrt_runtime import XrtSession

class SDK:
    def __init__(self, ready=False): self.events=[]; self.ready=ready; self.stamp=0
    def init(self): self.events.append('init')
    def close(self): self.events.append('close')
    def is_body_data_available(self): return self.ready
    def get_time_stamp_ns(self): return 900
    def get_body_timestamp_ns(self): return 0
    def get_body_joints_timestamp(self):
        self.stamp += 1
        return [1_000_000_000 + ((self.stamp - 1)//2)*1_000_000]*24 if self.ready else [0]*24
    def get_body_joints_pose(self): return [[0,0,0,0,0,0,1]]*24

class Tests(unittest.TestCase):
    def session(self, sdk):
        return XrtSession(sdk, timeout=.08, poll_interval=.005, manage_service=False, lock_path=None)
    def test_missing_service_does_not_initialize_sdk(self):
        sdk=SDK()
        with patch('gear_sonic.utils.teleop.xrt_runtime.ensure_pc_service', side_effect=TimeoutError('service down')):
            with self.assertRaises(TimeoutError): self.session(sdk).start()
        self.assertEqual(sdk.events,[])
    @patch('gear_sonic.utils.teleop.xrt_runtime.ensure_pc_service')
    def test_no_body_times_out_and_closes_once(self, _):
        sdk=SDK(); s=self.session(sdk)
        with self.assertRaisesRegex(TimeoutError,'Full Body'): s.start()
        s.close(); self.assertEqual(sdk.events,['init','close'])
    @patch('gear_sonic.utils.teleop.xrt_runtime.ensure_pc_service')
    def test_readers_stop_before_sdk_close(self, _):
        sdk=SDK(True); s=self.session(sdk); s.start()
        class Reader:
            def stop(self): sdk.events.append('reader-stop')
        s.add_reader(Reader()); s.close(); s.close()
        self.assertEqual(sdk.events,['init','reader-stop','close'])
    @patch('gear_sonic.utils.teleop.xrt_runtime.ensure_pc_service')
    def test_latched_body_flag_with_stale_timestamp_is_not_ready(self, _):
        sdk=SDK(True); sdk.get_body_joints_timestamp=lambda:[7]*24
        with self.assertRaises(TimeoutError): self.session(sdk).start()
        self.assertEqual(sdk.events,['init','close'])
    @patch('gear_sonic.utils.teleop.xrt_runtime.ensure_pc_service')
    def test_malformed_pose_rejected(self, _):
        sdk=SDK(True); sdk.get_body_joints_pose=lambda: [[0]*7]*23
        with self.assertRaises(TimeoutError): self.session(sdk).start()
        self.assertEqual(sdk.events,['init','close'])
    @patch('gear_sonic.utils.teleop.xrt_runtime.ensure_pc_service')
    def test_interrupt_closes_sdk(self, _):
        sdk=SDK(); sdk.is_body_data_available=lambda: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt): self.session(sdk).start()
        self.assertEqual(sdk.events,['init','close'])

    @patch('gear_sonic.utils.teleop.xrt_runtime.service_pids',return_value=[123])
    @patch('gear_sonic.utils.teleop.xrt_runtime.socket.create_connection')
    @patch('gear_sonic.utils.teleop.xrt_runtime.subprocess.Popen')
    def test_existing_service_reused(self, launch, connect, pids):
        from gear_sonic.utils.teleop.xrt_runtime import ensure_pc_service
        ensure_pc_service(timeout=.1)
        launch.assert_not_called();connect.assert_called_once()

    @patch('gear_sonic.utils.teleop.xrt_runtime.service_pids',return_value=[123,124])
    @patch('gear_sonic.utils.teleop.xrt_runtime.subprocess.Popen')
    def test_duplicate_service_fails_without_killing_or_starting(self, launch, pids):
        from gear_sonic.utils.teleop.xrt_runtime import ensure_pc_service
        with self.assertRaisesRegex(RuntimeError,'Multiple'):ensure_pc_service(timeout=.1)
        launch.assert_not_called()

    @patch('gear_sonic.utils.teleop.xrt_runtime.service_pids',return_value=[])
    @patch('gear_sonic.utils.teleop.xrt_runtime.subprocess.Popen')
    def test_require_existing_does_not_spawn(self, launch, pids):
        from gear_sonic.utils.teleop.xrt_runtime import ensure_pc_service
        with self.assertRaises(RuntimeError):ensure_pc_service(manage_service=False)
        launch.assert_not_called()

if __name__=='__main__': unittest.main()
