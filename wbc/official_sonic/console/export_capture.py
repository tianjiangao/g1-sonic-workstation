"""Export the newest complete raw episode using the existing isolated exporter."""
import json
from pathlib import Path
import subprocess
from official_sonic.console.backend import ConfigStore,CAPTURE_HOME

def latest_complete(root):
    candidates=[]
    for path in Path(root).glob('SESSION_*/episode_*/episode.json'):
        meta=json.loads(path.read_text())
        if meta.get('complete') and meta.get('frames',0)>=2:candidates.append(path.parent)
    if not candidates:raise RuntimeError('还没有可导出的完整片段，请先录制并保存至少2帧。')
    return sorted(candidates)[-1]

def main():
    c=ConfigStore().load();episode=latest_complete(Path(c.output)/c.dataset)
    output=episode.parent/('LEROBOT_'+episode.name)
    if output.exists():raise RuntimeError('该段已存在导出目录：'+str(output)+'；保留原数据，不覆盖。')
    print('正在导出：'+str(episode),flush=True)
    subprocess.run([str(CAPTURE_HOME/'capture/export.sh'),'--episode',str(episode),'--output',str(output)],check=True)
    print('导出并回读完成：'+str(output),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('导出未完成：'+str(e))
