import hashlib
from pathlib import Path
import socket
import tempfile
import unittest

from official_sonic.console import camera_autostart as camera


class CameraAutostartTests(unittest.TestCase):
    def test_changed_or_missing_source_refuses_launch(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / 'start_three.sh'
            source.write_bytes(b'reviewed camera command')
            hashes = {'start_three.sh': hashlib.sha256(source.read_bytes()).hexdigest()}
            camera.verify_sources(base, hashes)
            source.write_bytes(b'changed command')
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                camera.verify_sources(base, hashes)
            source.unlink()
            with self.assertRaises((OSError, RuntimeError)):
                camera.verify_sources(base, hashes)

    def test_unknown_listener_refuses_launch_without_touching_listener(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with self.assertRaisesRegex(RuntimeError, 'occupied'):
                camera.verify_idle(Path('/nonexistent-proc'), listener.getsockname()[1])
            self.assertTrue(listener.fileno() >= 0)

    def test_existing_camera_even_before_port_is_bound_refuses_duplicate(self):
        with tempfile.TemporaryDirectory() as d, socket.socket() as reserve:
            proc = Path(d) / '123'
            proc.mkdir()
            (proc / 'cmdline').write_bytes(b'python\0-m\0gear_sonic.camera.composed_camera\0')
            reserve.bind(('127.0.0.1', 0))
            with self.assertRaisesRegex(RuntimeError, '123'):
                camera.verify_idle(Path(d), reserve.getsockname()[1])

    def test_preview_waiting_live_and_stale_are_distinct(self):
        self.assertIn('SSH', camera.preview_note(None, 100))
        info = {'received_at': 99.8, 'shape': [480, 640, 3]}
        self.assertTrue(camera.preview_note(info, 100).startswith('实时'))
        self.assertIn('断流', camera.preview_note(info, 102))
        self.assertIn('异常', camera.preview_note(info, 98))


if __name__ == '__main__':
    unittest.main()
