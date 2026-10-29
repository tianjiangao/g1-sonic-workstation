"""Bounded read-only resource sampling of this owned simulation instance."""
import json
import os
from pathlib import Path
import subprocess
import time
from sim_teleop.runner import STATE,alive
s=json.loads(STATE.read_text());run=Path(s['run']);prev={};last=time.monotonic();hz=os.sysconf('SC_CLK_TCK')
with (run/'resources.jsonl').open('a',buffering=1) as out:
 while alive(s):
  now=time.monotonic();rows={}
  try:targets=json.loads((run/'children.json').read_text())['pids']+[s['pid'],s['namespace_pid'],s['relay_pid']]
  except OSError:targets=[]
  for pid in targets:
   try:
    fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();ticks=int(fields[11])+int(fields[12])
    rows[pid]={'cpu_percent_one_core':100*(ticks-prev.get(pid,ticks))/hz/(now-last),
               'rss_mib':int(fields[21])*os.sysconf('SC_PAGE_SIZE')/2**20}
    prev[pid]=ticks
   except OSError:pass
  gpu=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True)
  out.write(json.dumps({'host_monotonic':now,'processes':rows,'gpu_total_memory_mib_and_util_percent':gpu.stdout.strip()})+'\n')
  last=now;time.sleep(1)
