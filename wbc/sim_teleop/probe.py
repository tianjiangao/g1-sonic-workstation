"""Bounded read-only SDK observation; emit no device IDs or full poses."""
import argparse
import json
from pathlib import Path
import time
from gear_sonic.utils.teleop.xrt_runtime import XrtSession
from gear_sonic.utils.teleop.body_freshness import read_body_snapshot
import xrobotoolkit_sdk as xrt


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=8);p.add_argument('--output',required=True)
    a=p.parse_args(); s=XrtSession(xrt,timeout=5,manage_service=False)
    try:
        s.open();end=time.monotonic()+a.seconds
        while time.monotonic()<end:
            try:
                pose,t,available=read_body_snapshot(xrt)
                s.freshness.update(pose,t,available)
            except Exception as e:s.freshness.invalidate(type(e).__name__+':'+str(e))
            time.sleep(.01)
        stats=s.freshness.stats()
        stats['overall_timestamp_ns']=int(xrt.get_body_timestamp_ns())
        Path(a.output).write_text(json.dumps(stats,indent=2))
        print('SDK_PROBE',stats['accepted_frames'],stats['reason'],flush=True)
        return 0 if stats['accepted_frames']>=20 and s.freshness.latest() is not None else 2
    finally:s.close()

if __name__=='__main__':raise SystemExit(main())
