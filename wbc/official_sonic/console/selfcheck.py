"""Exercise the upstream exporter offline, using clearly marked synthetic data.

No robot, SDK, DDS participant, model inference or network publisher is created.
"""
import argparse
from datetime import datetime
import importlib.metadata
import json
import os
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-root',required=True);a=p.parse_args()
    os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_DATASETS_OFFLINE']='1'
    import av
    import numpy as np
    import pyarrow.parquet as pq
    from gear_sonic.data.exporter import Gr00tDataExporter
    from gear_sonic.data.features_sonic_vla import (get_g1_robot_model,get_features_sonic_vla,
        get_modality_config_sonic_vla,get_wrist_camera_features,get_wrist_camera_modality_config)
    path=Path(a.output_root)/('SYNTHETIC_ONLY_'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    rm=get_g1_robot_model();features=get_features_sonic_vla(rm);features.update(get_wrist_camera_features())
    modality=get_modality_config_sonic_vla(rm)
    for key,value in get_wrist_camera_modality_config().items():modality.setdefault(key,{}).update(value)
    dataset=Gr00tDataExporter.create(save_root=path,fps=50,features=features,modality_config=modality,
        task='SYNTHETIC ENCODER SELFTEST - NOT ROBOT DATA',
        script_config={'synthetic_test_only':True,'real_robot_data':False},overwrite_existing=False)
    (path/'SYNTHETIC_TEST_ONLY.txt').write_text('合成格式与编码自检。没有采集机器人动作，不得作为真机验收或训练数据。\n')
    frames=12
    for i in range(frames):
        frame={}
        for key,ft in features.items():
            if ft['dtype']=='video':
                value=np.zeros(ft['shape'],dtype=np.uint8);value[:,:,i%3]=30+i*12
            else:
                value=np.zeros(ft['shape'],dtype=ft['dtype'])
                if key.endswith('root_orientation'):value[0]=1
            frame[key]=value
        dataset.add_frame(frame)
    dataset.save_episode()
    # save_episode opens writers for a next episode; close those without adding data.
    dataset.stop_video_writers()
    info=json.loads((path/'meta/info.json').read_text())
    assert info['total_episodes']==1 and info['total_frames']==frames,info
    table=pq.read_table(path/dataset.meta.get_data_file_path(0));assert table.num_rows==frames
    timestamps=table['timestamp'].to_numpy();assert np.allclose(np.diff(timestamps),.02,atol=1e-6)
    videos={}
    for key in dataset.meta.video_keys:
        video=path/dataset.meta.get_video_file_path(0,key)
        with av.open(str(video)) as container:
            stream=container.streams.video[0];rate=float(stream.average_rate)
            count=sum(1 for _ in container.decode(video=0))
        assert count==frames and rate==50,(key,count,rate)
        videos[key]={'decoded_frames':count,'fps':rate,'path':str(video)}
    result={'result':'PASS','synthetic_test_only':True,'real_robot_verified':False,
        'dataset':str(path),'episodes':1,'frames':frames,'video_streams':videos,
        'packages':{n:importlib.metadata.version(n) for n in ['lerobot','torch','torchvision','datasets','av','numpy']}}
    (path/'selfcheck-result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
