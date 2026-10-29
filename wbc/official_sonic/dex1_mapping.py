"""PICO input adapter to Unitree's unchanged Dex1 5..7 pinch input scale."""
import math

def load_routes(path=None):
    import json
    from pathlib import Path
    path=Path(path) if path else Path(__file__).parent/'profiles/dex1-hardware.json'
    routes=json.loads(path.read_text())['physical_to_wire']
    if set(routes)!={'left','right'} or set(routes.values())!={'left','right'}:
        raise ValueError('Dex1 routes must map each physical side to one unique wire side')
    return routes

def validate_feedback(q,dq,tau):
    # Encoder feedback can cross the commanded endpoint during deceleration.
    # The official motor loop uses measured position, not a [0,5.4] sensor range.
    # Enforce finite feedback here; validate every outgoing command separately.
    if not all(math.isfinite(v) for v in (q,dq,tau)):
        raise ValueError('nonfinite Dex1 feedback')

def map_triggers(left,right,openings=(5.4,5.4)):
    for x in (left,right):
        if type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1:
            raise ValueError('PICO trigger must be finite numeric 0..1')
    if len(openings)!=2 or any(type(q) not in (int,float) or not math.isfinite(q) or not 0<=q<=5.4 for q in openings):
        raise ValueError('Dex1 opening must be finite 0..5.4 rad')
    # Unitree: pinch 5 => q=0 (closed), pinch 7 => q=5.4 (open).
    # On hardware the neutral opening is captured at session start, so the
    # first light squeeze closes from that pose rather than jumping fully open.
    return tuple(5.+2.*q/5.4*(1.-trigger) for q,trigger in zip(openings,(left,right)))

class TriggerTargets:
    """Hold until each hand is used; release then requests official full opening.

    Each new squeeze closes from measured position, including when reopening
    has not finished. The upstream loop still filters and limits every step.
    """
    def __init__(self,openings,return_to_start=False,auto_open=False):
        map_triggers(0,0,openings)
        self.limits=tuple(openings) if return_to_start else (5.4,5.4)
        self.activated={'left':bool(auto_open),'right':bool(auto_open)}
        self.pressing=[False,False];self.references=list(openings)
        self.opening_pending=[bool(auto_open),bool(auto_open)];self.opening_q=list(openings)

    def advance(self,left,right,positions,dt=0.):
        map_triggers(left,right)
        if not math.isfinite(dt) or dt<0:raise ValueError('invalid opening interval')
        if len(positions)!=2 or any(type(q) not in (int,float) or not math.isfinite(q) for q in positions):
            raise ValueError('invalid Dex1 measured opening')
        measured=[min(5.4,max(0.,q)) for q in positions]
        inputs=[]
        for i,(side,trigger) in enumerate(zip(('left','right'),(left,right))):
            if trigger>.1 and not self.pressing[i]:
                self.references[i]=min(self.limits[i],measured[i])
                self.pressing[i]=True;self.activated[side]=True
                self.opening_pending[i]=False
            elif trigger<=.05:
                self.pressing[i]=False
            if not self.activated[side]:q=measured[i]
            elif self.pressing[i]:q=self.references[i]*(1.-trigger)
            else:q=self.limits[i]
            if self.opening_pending[i]:
                self.opening_q[i]=min(self.limits[i],self.opening_q[i]+.5*min(dt,.05))
                q=self.opening_q[i]
                if q>=self.limits[i]:self.opening_pending[i]=False
            inputs.append(5.+q/2.7)
        return tuple(inputs)

class TrialLimiter:
    """Conservative commissioning envelope, not mechanical calibration.

    Never open beyond the captured start or command the zero endpoint. Keep
    upstream Unitree filtering intact; limit its input target slew separately.
    """
    def __init__(self,openings):
        map_triggers(0,0,openings=openings)
        self.openings=tuple(openings);self.q=list(openings)
    def advance(self,inputs,dt):
        if len(inputs)!=2 or not all(math.isfinite(x) and 5<=x<=7 for x in inputs):
            raise ValueError('invalid upstream pinch input')
        if not math.isfinite(dt) or dt<0:raise ValueError('invalid limiter interval')
        step=.5*min(dt,.05)
        for i,value in enumerate(inputs):
            floor=min(.15,self.openings[i])
            target=max(floor,min(self.openings[i],(value-5.)*2.7))
            self.q[i]+=max(-step,min(step,target-self.q[i]))
        return tuple(5.+q/2.7 for q in self.q)

class InputGate:
    def __init__(self):
        self.mode=0;self.manager_at=None;self.packet=None;self.sequence=-1;self.received_at=None
    def update_manager(self,mode,now):
        self.mode=int(mode);self.manager_at=now
    def update_trigger(self,packet,now):
        map_triggers(packet.get('left'),packet.get('right'))
        stamp=packet.get('timestamp_monotonic');seq=packet.get('sequence')
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=now-stamp<.25:
            raise ValueError('stale/future PICO body frame')
        if type(seq) is not int or seq<=self.sequence:raise ValueError('replayed PICO trigger frame')
        self.sequence=seq;self.packet=packet;self.received_at=now
    def allowed(self,now):
        return bool(self.mode in (1,2,3,5) and self.packet is not None and
            self.manager_at is not None and 0<=now-self.manager_at<.25 and
            self.received_at is not None and 0<=now-self.received_at<.25 and
            0<=now-self.packet['timestamp_monotonic']<.25)
