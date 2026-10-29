"""Launch an optional viewer, print its URL, stop only its process on Ctrl-C."""
import argparse,json
from offline_replay.launcher import launch
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--episode',required=True)
    args=parser.parse_args();handle=launch(args.episode)
    try:
        print(json.dumps(handle.wait_ready(),ensure_ascii=False,indent=2),flush=True)
        handle.process.wait()
    except KeyboardInterrupt:pass
    finally:handle.stop()
if __name__=='__main__':main()
