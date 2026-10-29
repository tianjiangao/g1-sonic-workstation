"""Isolated kinematic checks, contacts and synthetic gripper sequence. No DDS."""
import os
os.environ.setdefault('MUJOCO_GL','egl');os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE','1')
os.environ.setdefault('__EGL_VENDOR_LIBRARY_FILENAMES','/usr/share/glvnd/egl_vendor.d/50_mesa.json');os.environ.setdefault('LP_NUM_THREADS','2')
import argparse,json,math,subprocess
from pathlib import Path
import cv2,numpy as np,mujoco
from offline_replay.core import ROOT,BodyModel,NAMES,MODEL_DIR

def isolated():
    host=os.environ.get('SONIC_HOST_NETNS');current=os.readlink('/proc/self/ns/net')
    links=json.loads(subprocess.check_output(['ip','-j','link']))
    if not host or current==host or {x['ifname'] for x in links}!={'lo'}:raise RuntimeError('Require separate loopback-only network namespace')
    route=subprocess.run(['ip','route','get','192.168.123.164'],capture_output=True,text=True)
    if route.returncode==0:raise RuntimeError('Robot route exists')
    return {'host_netns':host,'current_netns':current,'interfaces':['lo'],'robot_route':route.stderr.strip()}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();network=isolated()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    old=mujoco.MjModel.from_xml_path(str(ROOT/'gear_sonic/data/robot_model/model_data/g1/scene_43dof.xml'))
    active=mujoco.MjModel.from_xml_path(str(MODEL_DIR/'g1_sonic_dex1.xml'));model=BodyModel()
    assert active.nu==33 and active.nq==40 and model.model.nu==0
    body_motors=[mujoco.mj_id2name(active,mujoco.mjtObj.mjOBJ_JOINT,int(active.actuator_trnid[i,0])) for i in range(29)]
    assert tuple(body_motors)==NAMES
    for name in NAMES:
        j1=mujoco.mj_name2id(old,mujoco.mjtObj.mjOBJ_JOINT,name);j2=mujoco.mj_name2id(active,mujoco.mjtObj.mjOBJ_JOINT,name)
        for attr in ('jnt_axis','jnt_pos','jnt_range'):np.testing.assert_allclose(getattr(old,attr)[j1],getattr(active,attr)[j2],atol=1e-7)
        for attr in ('body_pos','body_quat'):np.testing.assert_allclose(getattr(old,attr)[old.jnt_bodyid[j1]],getattr(active,attr)[active.jnt_bodyid[j2]],atol=1e-7)
    assert np.all(active.body_mass[1:]>0) and np.all(active.body_inertia[1:]>0)
    for side in ('left','right'):
        ids=[mujoco.mj_name2id(active,mujoco.mjtObj.mjOBJ_JOINT,f'{side}_dex1_finger_joint_{k}') for k in (1,2)]
        np.testing.assert_allclose(active.jnt_axis[ids[0]],-active.jnt_axis[ids[1]])
        for j in ids:
            assert active.jnt_type[j]==mujoco.mjtJoint.mjJNT_SLIDE
            np.testing.assert_allclose(active.jnt_range[j],[-.02,.0245])
    frames=[];snapshots=[];contacts=[]
    states=[('both_closed',[0.,0.]),('left_open',[5.4,0.]),('right_open',[0.,5.4]),('both_open',[5.4,5.4])]
    try:
        for label,dex in states:
            rgb=model.render([0.]*29,azimuth=135,elevation=-12,distance=2.6,dex1=dex)
            image=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR);cv2.putText(image,'SYNTHETIC_ONLY: '+label,(12,25),cv2.FONT_HERSHEY_SIMPLEX,.55,(20,80,160),1)
            cv2.imwrite(str(out/(label+'.png')),image);snapshots.append(image)
            # Only finger/finger collisions within one gripper: attached housing
            # overlaps and whole-body contacts are separate dynamics questions.
            for c in model.data.contact[:model.data.ncon]:
                names=[mujoco.mj_id2name(model.model,mujoco.mjtObj.mjOBJ_BODY,int(model.model.geom_bodyid[g])) for g in (c.geom1,c.geom2)]
                if all('_dex1_finger_' in n for n in names):contacts.append({'state':label,'bodies':names,'distance':float(c.dist)})
        for side in ('left','right'):
            for label,dex in [('closed',[0.,0.]),('open',[5.4,5.4])]:
                rgb=model.render([0.]*29,azimuth=135,elevation=-15,dex1=dex,view=side)
                cv2.imwrite(str(out/(side+'_'+label+'_closeup.png')),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        for k in range(101):
            t=k/20;dex=[2.7*(1+math.sin(t*math.pi)),2.7*(1-math.sin(t*math.pi))]
            model.apply([0.]*29,dex)
            frames.append({'kind':'SYNTHETIC_ONLY','t_s':t,'raw_motor_rad':dex,'visual_slide_m':model.last_gripper['joints']})
        cv2.imwrite(str(out/'gripper_montage.png'),np.concatenate([np.concatenate(snapshots[:2],axis=1),np.concatenate(snapshots[2:],axis=1)],axis=0))
        assert not any(c['distance']<-.001 for c in contacts),contacts
        (out/'synthetic_gripper_sequence.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in frames))
        loaded=[json.loads(line) for line in (out/'synthetic_gripper_sequence.jsonl').read_text().splitlines()]
        for frame in loaded:
            assert frame['kind']=='SYNTHETIC_ONLY'
            model.apply([0.]*29,frame['raw_motor_rad'])
            assert model.last_gripper['joints']==frame['visual_slide_m']
        report={'result':'PASS_ISOLATED_KINEMATIC_MODEL','network':network,'renderer':model.gl_renderer,'body_joint_names':NAMES,
            'body_mapping_unchanged':True,'body_actuators':29,'finger_slides':4,'active_model_nu':33,'passive_model_nu':0,
            'symmetric_total_slide_travel_m':.089,'limits_m':[-.020,.0245],'finger_contacts':contacts,'synthetic_frames':101,
            'synthetic_frames_loaded_from_file':len(loaded),'dynamics_policy_run':False,'grasp_success_verified':False,'physical_motor_to_jaw_calibration':'nominal, not measured',
            'closure_gap_note':'Reference documents about 5.88mm pad gap with official URDF limit; no -0.023m closure trim used.'}
        (out/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:model.close()
if __name__=='__main__':main()
