"""Official MuJoCo wrapper with recorded state and automatic simulation tether release."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from gear_sonic.scripts.run_sim_loop import SimWrapper
from gear_sonic.utils.mujoco_sim.configs import SimLoopConfig
from gear_sonic.utils.mujoco_sim.simulator_factory import SimulatorFactory
from gear_sonic.data.robot_model.instantiation.g1 import instantiate_g1_robot_model
from sim_teleop.runner import write_json
from sim_teleop.safety import assert_isolated

def main():
    assert_isolated();p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--headless',action='store_true');a=p.parse_args()
    run=Path(a.run);config=SimLoopConfig(interface='sim',enable_onscreen=not a.headless)
    cfg=config.load_wbc_yaml();cfg['ENV_NAME']=config.env_name
    wrapper=SimWrapper(instantiate_g1_robot_model(),config.env_name,cfg,onscreen=not a.headless,offscreen=False)
    env=wrapper.sim.sim_env;original=env.sim_step;count=0;last=time.monotonic();max_step=0
    trace=(run/'sim-state.jsonl').open('a',buffering=1)
    def step():
        nonlocal count,last,max_step
        if env.elastic_band and env.elastic_band.enable and (run/'policy-active').exists():
            env.elastic_band.enable=False
            print('SIM_TETHER_RELEASED: first policy inference observed',flush=True)
        before=time.monotonic();original();after=time.monotonic();max_step=max(max_step,after-before);count+=1
        if not np.isfinite(env.mj_data.qpos).all() or not np.isfinite(env.mj_data.qvel).all():
            raise RuntimeError('Nonfinite MuJoCo state')
        if count%10==0:
            data={'host_monotonic':after,'sim_time':float(env.mj_data.time),'qpos':env.mj_data.qpos.tolist(),
                  'body_q':env.obs['body_q'].tolist(),'tether_enabled':bool(env.elastic_band and env.elastic_band.enable)}
            trace.write(json.dumps(data)+'\n')
        if after-last>=1:
            write_json(run/'sim-health.json',{'steps':count,'sim_time':float(env.mj_data.time),
                       'root_height_m':float(env.mj_data.qpos[2]),'max_step_compute_s':max_step,
                       'tether_enabled':bool(env.elastic_band and env.elastic_band.enable),'last_monotonic':after})
            last=after
    env.sim_step=step
    try:SimulatorFactory.start_simulator(wrapper.sim,as_thread=False)
    finally:trace.close()

if __name__=='__main__':main()
