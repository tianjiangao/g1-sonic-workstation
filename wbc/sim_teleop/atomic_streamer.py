"""Reuse official SONIC mapping/manager with a callback-atomic Pico reader."""
import argparse
import signal
import time
from pathlib import Path
from sim_teleop.process_reader import ProcessPicoReader
from sim_teleop.runner import write_json
from sim_teleop.safety import assert_isolated

def main():
    assert_isolated()
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--probe',action='store_true')
    a=p.parse_args();reader=ProcessPicoReader(a.output)
    def interrupt(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupt)
    try:
        if a.probe:
            reader.start()
            reader.wait_ready()
            time.sleep(3)
            if reader.disconnected:raise RuntimeError(reader.gate.reason)
            print('ATOMIC_PICO_PROBE PASS',flush=True);return
        from gear_sonic.scripts.pico_manager_thread_server import run_pico_manager
        run_pico_manager(bind_host='127.0.0.1',reader=reader)
    finally:
        write_json(Path(a.output),reader.freshness_stats());reader.stop()

if __name__=='__main__':main()
