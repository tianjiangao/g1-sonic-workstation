"""Register the official custom embodiment before invoking an upstream entrypoint."""
import argparse,runpy,sys
from sonic_pipeline.settings import GROOT
from sonic_pipeline.dex1_modality import CONFIG
p=argparse.ArgumentParser();p.add_argument('stage',choices=['evaluate','serve']);a,rest=p.parse_known_args()
file=GROOT/('gr00t/eval/open_loop_eval.py' if a.stage=='evaluate' else 'gr00t/eval/run_gr00t_server.py');sys.argv=[str(file)]+rest;runpy.run_path(str(file),run_name='__main__')
