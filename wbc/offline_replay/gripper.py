"""Physical-side 2x1D Dex1 motor radians -> four named visual slides (metres).
This is an independent nominal kinematic adapter, never a motor publisher.
"""
import math
class GripperStateAdapter:
    motor_range_rad=(0.,5.4)
    slide_range_m=(-.020,.0245)
    def map(self,raw,source='feedback'):
        if set(raw)!= {'left','right'} or source not in ('feedback','command'):raise ValueError('Require explicit physical left/right and feedback/command source')
        for value in raw.values():
            if type(value) not in (float,int) or not math.isfinite(value) or not -.05<=value<=5.45:raise ValueError('Invalid Dex1 motor radians; cannot infer/calibrate units')
        joints={};clipped=[]
        for side,value in raw.items():
            ratio=min(1.,max(0.,value/5.4))
            if not 0<=value<=5.4:clipped.append(side)
            position=(self.slide_range_m[0] if ratio==0 else self.slide_range_m[1] if ratio==1 else self.slide_range_m[0]+ratio*(self.slide_range_m[1]-self.slide_range_m[0]))
            for finger in (1,2):joints[f'{side}_dex1_finger_joint_{finger}']=position
        return {'source':source,'raw_motor_rad':dict(raw),'joints':joints,'display_clipped':clipped,
            'mapping':'nominal linear visual range; physical gearbox/aperture calibration unverified',
            'body_action_dimension':29,'real_gripper_action_dimension':2,'visual_finger_dofs':4}
