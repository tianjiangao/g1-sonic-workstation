import hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from official_sonic.console import remote_prepare as prep

class ModelContractTests(unittest.TestCase):
    def test_missing_member_never_falls_back_to_release(self):
        self.assertTrue(callable(getattr(prep,'verify_model',None)))
        with tempfile.TemporaryDirectory() as directory,patch.object(prep,'BASE',Path(directory)):
            with self.assertRaisesRegex(RuntimeError,'v1.1'):prep.verify_model()
    def test_triplet_hashes_are_verified_and_mismatch_is_rejected(self):
        self.assertTrue(callable(getattr(prep,'verify_model',None)))
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);model=base/'policy/sonic_v1_1';model.mkdir(parents=True)
            hashes={}
            for name in ('model_encoder.onnx','model_decoder.onnx','observation_config.yaml'):
                data=name.encode();(model/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
            with patch.object(prep,'BASE',base),patch.object(prep,'MODEL_HASHES',hashes):
                self.assertEqual(prep.verify_model()['hashes'],hashes)
                (model/'model_decoder.onnx').write_bytes(b'wrong checkpoint')
                with self.assertRaisesRegex(RuntimeError,'v1.1'):prep.verify_model()
