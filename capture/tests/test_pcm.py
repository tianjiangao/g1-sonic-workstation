import unittest
from pathlib import Path
from capture.robot_audio import play_pcm
from capture.pcm import synthesize

class StreamClient:
    def __init__(self,code=0):self.parts=[];self.code=code
    def PlayStream(self,app,stream,pcm):self.parts.append((app,stream,pcm));return self.code,''

class PcmTests(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).resolve().parents[1]/'voice/kokoro-int8-multi-lang-v1_1/model.int8.onnx').is_file() and (Path(__file__).resolve().parents[1]/'.venv_voice/bin/python').exists(), 'Optional voice model/runtime not bundled; run after voice setup')
    def test_chinese_synthesis_has_nonzero_bounded_16khz_pcm(self):
        import struct
        pcm=synthesize('开始采集，第1条')
        self.assertEqual(len(pcm)%2,0);self.assertGreater(len(pcm),32000);self.assertLess(len(pcm),320000)
        self.assertGreater(max(abs(x[0]) for x in struct.iter_unpack('<h',pcm)),100)
    def test_chunks_preserve_bytes_and_stream_identity(self):
        c=StreamClient();raw=b'\1\0'*50000;report=play_pcm(c,raw,pause=lambda _:None)
        self.assertEqual([len(x[2]) for x in c.parts],[96000,4000]);self.assertEqual(b''.join(x[2] for x in c.parts),raw)
        self.assertEqual(c.parts[0][1],c.parts[1][1]);self.assertFalse(report['audible_verified'])
    def test_failed_audio_rpc_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError,'3102'):play_pcm(StreamClient(3102),b'\0\0'*100,pause=lambda _:None)
