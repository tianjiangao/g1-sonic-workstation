import json
from pathlib import Path
import tempfile
import unittest
from official_sonic.console.export_capture import latest_complete

class ExportSelectionTests(unittest.TestCase):
    def test_partial_newest_does_not_hide_earlier_complete_episode(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for session,complete in [('SESSION_01',True),('SESSION_02',False)]:
                p=root/session/'episode_000000';p.mkdir(parents=True)
                (p/'episode.json').write_text(json.dumps({'complete':complete,'frames':3}))
            self.assertEqual(latest_complete(root),root/'SESSION_01/episode_000000')
    def test_empty_dataset_has_useful_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,'完整片段'):latest_complete(d)
