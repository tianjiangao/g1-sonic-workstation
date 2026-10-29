"""Offline Chinese speech using the existing system espeak-ng library."""
import audioop
import ctypes as C
import threading

_lock=threading.Lock()

def boost_pcm(pcm):
    """Raise speech body loudness with bounded gain and soft peak limiting.

    Process a copy at playback time; cached voice source stays unchanged.
    """
    if not pcm or len(pcm)%2:raise ValueError('invalid 16-bit mono PCM')
    import math,struct,sys
    from array import array
    peak=audioop.max(pcm,2);rms=audioop.rms(pcm,2);cap=int(32767*.92)
    gain=min(8.,max(1.,32767*.24/max(1,rms))) if peak>=32 else 1.
    if peak<32:result=pcm
    else:
        samples=array('h',(round(cap*math.tanh(x[0]*gain/cap)) for x in struct.iter_unpack('<h',pcm)))
        if sys.byteorder!='little':samples.byteswap()
        result=samples.tobytes()
    return result,{'gain':gain,'peak_before':peak,'peak_after':audioop.max(result,2),
                   'rms_before':rms,'rms_after':audioop.rms(result,2),'clipping_samples_added':False,
                   'compression':'soft_limit','target_rms_fraction':.24,'peak_limit_fraction':.92}

def espeak_synthesize(text):
    with _lock:
        lib=C.CDLL('libespeak-ng.so.1')
        lib.espeak_Initialize.argtypes=[C.c_int,C.c_int,C.c_char_p,C.c_int]
        rate=lib.espeak_Initialize(1,0,None,0)
        if rate<=0:raise RuntimeError('espeak initialization failed')
        chunks=[]
        callback_type=C.CFUNCTYPE(C.c_int,C.POINTER(C.c_short),C.c_int,C.c_void_p)
        @callback_type
        def receive(samples,count,events):
            if samples and count:chunks.append(C.string_at(samples,count*2))
            return 0
        lib.espeak_SetSynthCallback.argtypes=[callback_type];lib.espeak_SetSynthCallback(receive)
        lib.espeak_SetVoiceByName.argtypes=[C.c_char_p]
        if lib.espeak_SetVoiceByName(b'cmn')!=0:raise RuntimeError('Chinese voice unavailable')
        lib.espeak_Synth.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_int,C.c_uint,C.c_uint,C.POINTER(C.c_uint),C.c_void_p]
        data=text.encode('utf-8')+b'\0';buf=C.create_string_buffer(data);uid=C.c_uint()
        result=lib.espeak_Synth(buf,len(data),0,1,0,1,C.byref(uid),None)
        if result!=0:raise RuntimeError('speech synthesis failed '+str(result))
        lib.espeak_Synchronize();lib.espeak_Terminate()
        pcm=b''.join(chunks)
        if not pcm:raise RuntimeError('empty speech audio')
        return audioop.ratecv(pcm,2,1,rate,16000,None)[0]


def synthesize(text):
    """Use the configured local neural male voice; keep eSpeak as manual rollback."""
    import hashlib,subprocess
    from pathlib import Path
    root=Path(__file__).resolve().parent
    cache=root/'voice/pcm-cache';cache.mkdir(exist_ok=True)
    key=hashlib.sha256(('kokoro-v1.1-int8-sid58-speed1-'+text).encode()).hexdigest()
    dest=cache/(key+'.pcm')
    if not dest.exists():
        r=subprocess.run([str(root/'.venv_voice/bin/python'),str(root/'neural_voice.py'),'--text',text,'--output',str(dest)],capture_output=True,text=True,timeout=25)
        if r.returncode:raise RuntimeError('本地男声合成失败：'+r.stderr[-800:])
    data=dest.read_bytes()
    if not data or len(data)%2:raise ValueError('invalid cached PCM')
    return data
