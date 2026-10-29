"""Atomic display counters scoped to collection batches; raw episodes are immutable."""
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl,json,time,uuid
from pathlib import Path

def _new_id():return datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
def state(root):
    p=Path(root)/'take-counter.json'
    d=json.loads(p.read_text()) if p.exists() else {'last_number':0,'batch_id':'unstarted'}
    if type(d.get('last_number')) is not int or d['last_number']<0:raise ValueError('Invalid batch counter; refusing reset')
    d.setdefault('batch_id','legacy')
    return d
@contextmanager
def _locked(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with (root/'.counter.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX);yield root

def _write(root,d):
    p=root/'take-counter.json';tmp=root/('take-counter.'+str(time.time_ns())+'.tmp')
    tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2));tmp.replace(p)
def allocate(root):
    with _locked(root) as root:
        d=state(root)
        if d['batch_id']=='unstarted':d['batch_id']=_new_id()
        d['last_number']+=1;_write(root,d);return d

def finish(root):
    with _locked(root) as root:
        d=state(root);d['closed_at']=datetime.now(timezone.utc).isoformat()
        archive=root/'.batches';archive.mkdir(exist_ok=True)
        (archive/(str(time.time_ns())+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2))
        _write(root,{'last_number':0,'batch_id':_new_id()})
        return d
