import unittest
from capture.speech import send_robot_speech

class Client:
    def __init__(self,code=0):self.tts_index=0;self.calls=[];self.code=code
    def TtsMaker(self,text,speaker):
        self.tts_index+=self.tts_index;self.calls.append((text,speaker,self.tts_index));return self.code

class RobotSpeechTests(unittest.TestCase):
    def test_requests_chinese_voice_and_distinct_nonzero_indices(self):
        c=Client();send_robot_speech(c,'开始采集，第1条');send_robot_speech(c,'第1条已保存')
        self.assertEqual(c.calls[0][:2],('开始采集，第1条',0))
        self.assertGreater(c.calls[0][2],0);self.assertNotEqual(c.calls[0][2],c.calls[1][2])
    def test_rpc_rejection_is_not_reported_as_speech_success(self):
        with self.assertRaises(RuntimeError):send_robot_speech(Client(3102),'test')
