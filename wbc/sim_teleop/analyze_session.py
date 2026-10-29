"""Offline, reproducible summary of an actual simulation teleop session."""
import argparse
import json
from pathlib import Path
import re
import numpy as np

def main():
 p=argparse.ArgumentParser();p.add_argument('run');a=p.parse_args();run=Path(a.run)
 poses=[];debug=[]
 for line in (run/'telemetry.jsonl').open():
  d=json.loads(line)
  if d['topic']=='pose':poses.append(d)
  elif d['topic']=='g1_debug':debug.append(d)
 states=[json.loads(l) for l in (run/'sim-state.jsonl').open()]
 start=poses[0]['host_monotonic'];end=poses[-1]['host_monotonic'];states=[x for x in states if start<=x['host_monotonic']<=end]
 t=np.array([x['host_monotonic'] for x in poses]);st=np.array([x['host_monotonic'] for x in states]);q=np.array([x['body_q'] for x in states]);h=np.array([x['qpos'][2] for x in states])
 latency=np.array([x['host_monotonic']-x['data']['timestamp_monotonic'][0] for x in poses])
 timing=[float(v) for v in re.findall(r'Policy: (\d+)us', (run/'sonic.log').read_text(errors='replace'))]
 result={'session':str(run.resolve()),'pose_messages':len(poses),'pose_span_s':end-start,
         'observed_pose_message_hz':(len(poses)-1)/(end-start),'inference_debug_samples':len(debug),
         'receipt_to_zmq_ms':{k:float(np.percentile(latency,v)*1000) for k,v in [('p50',50),('p95',95),('p99',99)]},
         'policy_inference_us':{'p50':float(np.percentile(timing,50)),'p95':float(np.percentile(timing,95))} if timing else {},
         'measured_arm_joint_range_rad':{'left':np.ptp(q[:,15:22],axis=0).tolist(),'right':np.ptp(q[:,22:29],axis=0).tolist()},
         'root_height_m':{'min':float(h.min()),'max':float(h.max()),'first':float(h[0]),'last':float(h[-1])},
         'first_root_below_035m_after_pose_s':float(st[np.flatnonzero(h<.35)[0]]-start) if (h<.35).any() else None,
         'dds':json.loads((run/'dds.json').read_text()),'telemetry':json.loads((run/'telemetry.json').read_text()),
         'limitations':['receipt-to-ZMQ is not full action-to-robot latency','message frame-index gaps do not measure source network packet loss',
                        'root height alone cannot distinguish commanded crouch from fall','user visual confirmation is required for left-right correctness']}
 result['dds'].pop('joint_names_hardware_order',None)
 resources=run/'resources.jsonl'
 if resources.exists():
  data=[json.loads(l) for l in resources.open()];cpu=[];gpu=[]
  for row in data:
   cpu.append(sum(x['cpu_percent_one_core'] for x in row['processes'].values()))
   try:gpu.append([float(v.strip()) for v in row['gpu_total_memory_mib_and_util_percent'].split(',')])
   except (ValueError,KeyError):pass
  result['resources']={'sample_count':len(data),'aggregate_sampled_process_cpu_percent_one_core_p50':float(np.percentile(cpu,50)) if cpu else None,
                       'gpu_total_memory_mib_max':max((x[0] for x in gpu),default=None),'gpu_util_percent_p95':float(np.percentile([x[1] for x in gpu],95)) if gpu else None,
                       'note':'GPU totals include desktop; worker CPU not included in direct-child process sampler'}
 (run/'session-summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
