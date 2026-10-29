"""Offline adapter to the pinned upstream Gr00tDataExporter; no robot access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import cv2
import numpy as np
from capture.core import schema

WBC=Path('/opt/g1/GR00T-WholeBodyControl')

def export_episode(episode,output):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_DATASETS_OFFLINE']='1'
    sys.path.insert(0,str(WBC))
    from gear_sonic.data.exporter import Gr00tDataExporter
    path=Path(episode).resolve();out=Path(output).resolve()
    if out.exists():raise FileExistsError(out)
    meta=json.loads((path/'episode.json').read_text())
    if not meta['complete'] or meta['frames']<2:raise ValueError('only complete episodes with >=2 frames can export')
    context=json.loads((path/'context.json').read_text());session=context['session'];fps=session['fps']
    rows=[json.loads(line) for line in (path/'frames.jsonl').read_text().splitlines()]
    if len(rows)!=meta['frames']:raise ValueError('frame count mismatch')
    # Validate every image and numeric field before asking upstream to create output.
    features,modality=schema();previous=None
    for row in rows:
        if previous is not None and not .5e9/fps<=row['mono_ns']-previous<=2e9/fps:raise ValueError('invalid frame interval')
        previous=row['mono_ns']
        for key in ('observation.body','action.body','observation.dex1','action.dex1'):
            v=np.asarray(row[key],dtype=np.float32)
            if v.shape!=features[key]['shape'] or not np.isfinite(v).all():raise ValueError('invalid '+key)
        for role,relative in row['images'].items():
            image_path=(path/relative).resolve()
            if not image_path.is_relative_to(path):raise ValueError('image outside episode')
            image=image_path.read_bytes()
            if hashlib.sha256(image).hexdigest()!=image_path.stem:raise ValueError('image hash mismatch')
            decoded=cv2.imdecode(np.frombuffer(image,np.uint8),cv2.IMREAD_COLOR)
            if decoded is None or decoded.shape!=features['observation.images.'+role]['shape']:raise ValueError('invalid image '+role)
    exporter=Gr00tDataExporter.create(save_root=out,fps=fps,features=features,modality_config=modality,
        task=session['task'],script_config={'capture_schema':'g1-29-dex1-v1','source_session':session,
        'robot_config':context['latest']['robot_config']['data'],'timestamp_basis':'fixed grid; actual receipt times in source raw episode',
        'strict_sensor_synchronization':False,'body_order':'SONIC MuJoCo body_q / last_action (offset applied by upstream)',
        'action_semantics':'actual WBC body command plus observed physical Dex1 command q radians',
        'training_ready':False},robot_type='g1_29_dex1',overwrite_existing=False)
    try:
        for row in rows:
            frame={k:np.asarray(row[k],np.float32) for k in ('observation.body','action.body','observation.dex1','action.dex1')}
            for role,relative in row['images'].items():frame['observation.images.'+role]=cv2.imread(str(path/relative))[:,:,::-1].copy()
            exporter.add_frame(frame)
        exporter.save_episode()
    finally:exporter.stop_video_writers()
    import av
    import pyarrow.parquet as pq
    table=pq.read_table(out/exporter.meta.get_data_file_path(0))
    if table.num_rows!=len(rows):raise ValueError('parquet count mismatch')
    videos={}
    for key in exporter.meta.video_keys:
        with av.open(str(out/exporter.meta.get_video_file_path(0,key))) as c:
            rate=float(c.streams.video[0].average_rate);n=sum(1 for _ in c.decode(video=0))
        if n!=len(rows) or rate!=fps:raise ValueError('video count/rate mismatch')
        videos[key]={'frames':n,'fps':rate}
    report={'format_validation':'PASS','frames':len(rows),'videos':videos,'source_episode':str(path),
            'source_frames_sha256':hashlib.sha256((path/'frames.jsonl').read_bytes()).hexdigest(),
            'synthetic':session.get('synthetic',False),'training_ready':False,'real_motion_verified':False}
    (out/'capture-validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2));return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--episode',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();export_episode(a.episode,a.output)

if __name__=='__main__':main()
