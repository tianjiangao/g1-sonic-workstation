import importlib.util
from pathlib import Path
import tempfile
import unittest

P=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare',P/'tools/prepare.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PreparationTests(unittest.TestCase):
    def test_relocation_only_changes_documented_examples(self):
        self.assertEqual(m.relocate('/opt/g1/workspace /opt/g1/GR00T-WholeBodyControl /opt/g1/Isaac-GR00T /opt/g1/audio-env',Path('/tmp/site'),Path('/tmp/wbc'),Path('/tmp/groot'),Path('/tmp/audio')), '/tmp/site /tmp/wbc /tmp/groot /tmp/audio')
    def test_existing_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError):m.require_new(Path(d))
    def test_symlink_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'link';p.symlink_to(Path(d)/'missing')
            with self.assertRaises(FileExistsError):m.require_new(p)
    def test_overlay_collision_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'official_sonic').mkdir()
            with self.assertRaises(FileExistsError):m.require_overlay_absent(p)
    def test_source_paths_cannot_contain_shell_metacharacters(self):
        with self.assertRaises(ValueError):m.safe_path('/tmp/path;command')
    def test_pinned_revision_mismatch_rejected(self):
        from unittest.mock import patch
        with patch.object(m,'git',return_value='wrong'):
            with self.assertRaises(ValueError):m.check_revision(Path('/tmp/repo'),'expected')
if __name__=='__main__':unittest.main()
