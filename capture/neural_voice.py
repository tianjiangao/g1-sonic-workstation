"""Offline CPU Chinese male voice; pinned sherpa/Kokoro, no network or GPU."""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import sherpa_onnx
VOICE=Path(__file__).resolve().parent/'voice/kokoro-int8-multi-lang-v1_1'
def synthesize(text):
 config=sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(model=str(VOICE/'model.int8.onnx'),voices=str(VOICE/'voices.bin'),tokens=str(VOICE/'tokens.txt'),lexicon=str(VOICE/'lexicon-zh.txt')+','+str(VOICE/'lexicon-us-en.txt')),num_threads=2,provider='cpu'),rule_fsts=','.join(str(VOICE/f) for f in ['number-zh.fst','date-zh.fst','phone-zh.fst']))
 if not config.validate():raise ValueError('invalid voice configuration')
 tts=sherpa_onnx.OfflineTts(config);audio=tts.generate(text,sid=58,speed=1.)
 samples=np.asarray(audio.samples,dtype=np.float32)
 if samples.size<100 or not np.isfinite(samples).all() or np.max(np.abs(samples))<.001:raise ValueError('invalid neural voice audio')
 # Resample to the robot's required 16kHz mono, no extra dependencies.
 x=np.arange(round(len(samples)*16000/audio.sample_rate))*audio.sample_rate/16000
 out=np.interp(x,np.arange(len(samples)),samples)
 return (np.clip(out,-1,1)*32767).astype('<i2').tobytes()
def main():
 p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 pcm=synthesize(a.text);dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_name(dest.name+'.'+str(time.time_ns())+'.tmp');tmp.write_bytes(pcm);tmp.replace(dest)
 print(json.dumps({'speaker':'zm_009','sid':58,'engine':'Kokoro-v1.1-zh int8 / sherpa-onnx 2.0.1','duration_s':len(pcm)/32000,'bytes':len(pcm),'sha256':hashlib.sha256(pcm).hexdigest()}))
if __name__=='__main__':main()
