"""Audio-only helper, run with the existing isolated SDK environment."""
import argparse
import json
import time
from capture.pcm import synthesize,boost_pcm

def play_pcm(client,pcm,pause=time.sleep):
    if not pcm or len(pcm)%2:raise ValueError('invalid 16-bit mono PCM')
    stream=str(time.time_ns());sent=0
    for offset in range(0,len(pcm),96000):
        code,_=client.PlayStream('g1_capture',stream,pcm[offset:offset+96000])
        if code!=0:raise RuntimeError(f'G1 PlayStream failed code={code}, bytes_sent={sent}')
        sent+=len(pcm[offset:offset+96000]);pause(1)
    return {'rpc_accepted':True,'audible_verified':False,'bytes_sent':sent,'duration_s':len(pcm)/32000,'target':'robot_speaker_pcm','voice':'Kokoro v1.1 zh / zm_009 male / CPU'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--network',default='enp4s0');a=p.parse_args()
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
    pcm,levels=boost_pcm(synthesize(a.text))
    ChannelFactoryInitialize(0,a.network);c=AudioClient();c.SetTimeout(5);c.Init()
    for _ in range(4):
        code,volume=c.GetVolume()
        if code==0:break
        time.sleep(.5)
    else:raise RuntimeError('robot voice service unavailable')
    code=c.SetVolume(100)
    if code!=0:raise RuntimeError('设置机器人最大音量失败：'+str(code))
    code,volume=c.GetVolume()
    if code!=0 or volume.get('volume')!=100:raise RuntimeError('机器人最大音量核验失败')
    started=time.monotonic();result=play_pcm(c,pcm)
    time.sleep(max(0,result['duration_s']-(time.monotonic()-started))+.3)
    print(json.dumps(dict(result,text=a.text,volume=volume,audio_levels=levels),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
