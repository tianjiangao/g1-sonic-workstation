import audioop
import struct
import unittest
from capture import pcm

class AudioLevelTests(unittest.TestCase):
    def boost(self, data):
        self.assertTrue(hasattr(pcm,'boost_pcm'),'Speech PCM boost is missing')
        return pcm.boost_pcm(data)
    def test_quiet_pcm_becomes_louder_without_changing_length(self):
        data=struct.pack('<hhhh',0,4000,-4000,1000)*100
        loud,report=self.boost(data)
        self.assertEqual(len(loud),len(data))
        self.assertGreater(report['gain'],1.)
        self.assertGreater(audioop.max(loud,2),4000)
        self.assertGreater(audioop.rms(loud,2),audioop.rms(data,2))
    def test_louder_input_uses_headroom_instead_of_clipping(self):
        loud,report=self.boost(struct.pack('<hh',20000,-20000)*100)
        self.assertLessEqual(audioop.max(loud,2),30147)
        self.assertGreaterEqual(report['gain'],1.)
        self.assertLess(report['gain'],2.)
    def test_silence_and_near_silence_are_not_amplified(self):
        for data in (b'\0\0'*100,struct.pack('<hh',2,-2)*100):
            result,report=self.boost(data)
            self.assertEqual(result,data);self.assertEqual(report['gain'],1.)
    def test_bad_pcm_is_rejected(self):
        for data in (b'',b'\0'):
            with self.assertRaises(ValueError):self.boost(data)
    def test_full_scale_input_stays_bounded(self):
        result,report=self.boost(struct.pack('<hh',32767,-32768)*100)
        self.assertLessEqual(audioop.max(result,2),30147)
        self.assertLessEqual(report['gain'],1.)

class SpeechLoudnessTests(unittest.TestCase):
    def test_transient_peaks_do_not_keep_speech_body_quiet(self):
        values=[2000,-2000]*1000+[16000,-16000]
        data=struct.pack('<'+'h'*len(values),*values)
        loud,report=pcm.boost_pcm(data)
        linear=audioop.mul(data,2,30146/16000)
        self.assertGreater(audioop.rms(loud,2),audioop.rms(linear,2)*1.3)
        self.assertEqual(report.get('compression'),'soft_limit')
        self.assertLessEqual(audioop.max(loud,2),30147)
