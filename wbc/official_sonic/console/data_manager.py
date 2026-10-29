"""Offline data tools. No DDS, motor clients, or robot startup imports."""
import fcntl,json,sys,time,subprocess,socket
from pathlib import Path
from official_sonic.console.backend import CAPTURE_HOME
if str(CAPTURE_HOME) not in sys.path:sys.path.append(str(CAPTURE_HOME))
from capture.batches import state,finish
from capture.workbench import catalog,quality
STORE=CAPTURE_HOME/'datasets/workstation'
def dataset_root(config):return Path(config.output)/config.dataset
def finish_idle(config):
    with (CAPTURE_HOME/'capture/recorder.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('录制器仍运行，请在工作站结束本批次，不直接重置计数')
        return finish(dataset_root(config))
def annotations():
    p=STORE/'annotations.json';return json.loads(p.read_text()) if p.exists() else {}
def rows(config):
    reviews=annotations();result=catalog(dataset_root(config))
    for row in result:row.update(reviews.get(row['id'],{}))
    return result
def annotate(row,decision,reviewer,note):
    if decision not in ('success','failed','device_test','pending'):raise ValueError('无效人工标签')
    if not reviewer.strip() or not note.strip():raise ValueError('请填写审核人和依据／失败原因')
    all_reviews=annotations();all_reviews[row['id']]={'decision':decision,'reviewer':reviewer,'note':note,'reviewed_at':time.time()}
    STORE.mkdir(parents=True,exist_ok=True);p=STORE/'annotations.json'
    if p.exists():(STORE/('annotations.'+str(time.time_ns())+'.bak')).write_bytes(p.read_bytes())
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(all_reviews,ensure_ascii=False,indent=2));tmp.replace(p)
    return all_reviews[row['id']]
def check(row):
    report=quality(row['episode']);out=STORE/'quality';out.mkdir(parents=True,exist_ok=True)
    (out/(row['id']+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report

def replay(row):
    from sonic_pipeline.manifest import fingerprint
    from sonic_pipeline.review_page import build_review_page
    out=STORE/'replay'/(row['id']+'-'+str(time.time_ns()));out.parent.mkdir(parents=True,exist_ok=True)
    manifest=out.with_suffix('.manifest.json')
    manifest.write_text(json.dumps({'episodes':[dict(row,decision='pending',fingerprints=fingerprint(row['episode']))]},ensure_ascii=False))
    build_review_page(manifest,out)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with (out/'server.log').open('ab') as log:
        p=subprocess.Popen([sys.executable,'-m','http.server',str(port),'--bind','127.0.0.1','--directory',str(out)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    (out/'server.json').write_text(json.dumps({'pid':p.pid,'port':port,'scope':'offline replay only'}))
    return {'url':f'http://127.0.0.1:{port}/index.html','path':str(out),'pid':p.pid}
