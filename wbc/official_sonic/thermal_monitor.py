"""Bounded read-only diagnostic heuristic; never stops or commands motors."""
from collections import deque
import math

ANKLES=((4,'左踝俯仰'),(5,'左踝侧摆'),(10,'右踝俯仰'),(11,'右踝侧摆'))
def finite(values,n):
    return isinstance(values,list) and len(values)==n and all(type(x) in (int,float) and math.isfinite(x) for x in values)

class ThermalMonitor:
    def __init__(self):self.history=deque(maxlen=300)
    @property
    def history_size(self):return len(self.history)
    def update(self,data,now):
        temperatures=data.get('motor_temperature');q=data.get('body_q');target=data.get('last_action')
        if not finite(temperatures,58) or not finite(q,29) or not finite(target,29):raise ValueError('温度或实际/目标关节数据缺失或非有限')
        if not math.isfinite(now) or (self.history and now<=self.history[-1][0]):raise ValueError('热诊断接收时间非单调')
        self.history.append((now,q,temperatures))
        while len(self.history)>1 and self.history[1][0]<now-5:self.history.popleft()
        first=self.history[0];span=now-first[0];ankles=[];alerts=[]
        for index,name in ANKLES:
            raw=temperatures[index*2:index*2+2];peak=max(raw);error=abs(target[index]-q[index]);rate=None
            if span>=4.9:
                rate=(peak-max(first[2][index*2:index*2+2]))/span
            motion=max(x[1][index] for x in self.history)-min(x[1][index] for x in self.history)
            rapid=rate is not None and rate>=.8 and error>=.4 and motion<=.02
            if peak>=70 or rapid:alerts.append(f'{name} {peak:.0f}°C'+('，快速升温且实际关节变化小、PD目标偏差大' if rapid else '，温度升高'))
            ankles.append({'index':index,'name':name,'temperature_raw_C':raw,'peak_C':peak,'pd_target_error_rad':error,
                'rate_C_s':rate,'measured_span_rad':motion,'rapid_load_heating':rapid})
        return {'available':True,'ankles':ankles,'peak_C':max(temperatures),'alert':'；'.join(alerts),
            'window_s':span,'source':'host receipt time, reported motor temperatures; diagnostic only',
            'robot_commands_sent':0,'mechanical_failure_proven':False}
