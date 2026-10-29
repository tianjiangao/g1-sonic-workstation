"""Evidence-only startup state. No inputs, network clients or robot commands."""
import json,os,time
from pathlib import Path

class StartupStatus:
    def __init__(self):
        self.phase='WAITING';self.note='尚未开始';self.alert='';self.control=False;self.buffer='';self.thermal=None;self.started=time.monotonic()
    def set(self,phase,note):
        if not self.alert:self.phase=phase;self.note=note
    def feed(self,text):
        self.buffer+=text.replace('\r','')
        lines=self.buffer.split('\n');self.buffer=lines.pop()[-4096:]
        for line in lines:
            if '[HighTemp]' in line:
                self.alert=line.strip();self.phase='THERMAL_ALARM';self.note='温度报警：停止操作并按现场安全流程处理，不要摘吊架试走'
            if self.alert:continue
            if 'Init Done' in line:self.set('WAIT_ENABLE','INIT已完成；等待现场ABXY一次后松开，尚未证明IDLE或站立安全')
            elif 'operator_state.start=true' in line:
                self.control=True;self.set('CONTROL_STARTING','已收到现场启控；等待规划器状态，不重复发送启控')
            elif self.control and 'Replanning with mode: IDLE' in line:
                self.set('IDLE_REFERENCE','规划器已生成IDLE参考；仍需观察温度、反馈与身体状态')
            elif 'not found. This could take a while to generate' in line:
                self.set('MODEL_BUILD','正在生成TensorRT缓存，请等待，不要重复启动')
    def snapshot(self):
        return {'pid':os.getpid(),'phase':self.phase,'note':self.note,'alert':self.alert,'time_epoch':time.time(),
            'elapsed_s':time.monotonic()-self.started,'model':'SONIC v1.1','thermal':self.thermal,'physical_motion_verified':False}
    def observe_thermal(self,thermal):
        self.thermal=thermal
        if not thermal.get('alert') or self.phase=='THERMAL_ALARM':return
        self.alert=thermal['alert'];self.phase='THERMAL_ALARM' if thermal.get('peak_C',0)>=90 else 'THERMAL_RISK'
        self.note='热风险：停止操作并按现场安全流程处理；本监测不自动卸力，诊断提示不等于损坏结论'
    def write(self,path):
        path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(self.snapshot(),ensure_ascii=False));tmp.replace(path)
