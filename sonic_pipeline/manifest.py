"""Immutable-input fingerprints and explicit human review decisions."""
import hashlib,json
from pathlib import Path
FILES=('episode.json','context.json','frames.jsonl','events.jsonl')
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def fingerprint(episode):return {f:sha(Path(episode)/f) for f in FILES}
def inventory(raw,output):
 out=Path(output)
 if out.exists():raise FileExistsError('Review file exists; not overwriting decisions: '+str(out))
 entries=[]
 for meta in sorted(Path(raw).glob('SESSION_*/episode_*/episode.json')):
  ep=meta.parent;d=json.loads(meta.read_text());context=json.loads((ep/'context.json').read_text())
  entries.append({'take':d.get('take_number'),'episode':str(ep.resolve()),'fingerprints':fingerprint(ep),'decision':'unreviewed','reviewer':None,'review_note':'','task':context['session']['task'],'split':'unassigned','trim_start_s':0.,'trim_end_s':None,'complete':d.get('complete'),'raw_frames':d['frames']})
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({'schema':'sonic-review-v1','episodes':entries},ensure_ascii=False,indent=2));return {'episodes':len(entries),'approved':0,'manifest':str(out)}
def approved(manifest,split):
 doc=json.loads(Path(manifest).read_text());entries=[x for x in doc['episodes'] if x['decision']=='approved' and x['split']==split]
 if not entries:raise ValueError('No human-approved episodes for split '+split+'; raw test clips are not automatically training data')
 for e in entries:
  if not e.get('reviewer') or not e.get('review_note'):raise ValueError('Approved episode needs reviewer and review_note')
  if not e.get('task','').strip():raise ValueError('Task instruction required')
  if fingerprint(e['episode'])!=e['fingerprints']:raise ValueError('Raw files changed since review: '+e['episode'])
  if not e.get('complete'):raise ValueError('Incomplete episode cannot enter training')
 return entries

def record_review(manifest,output,episode,decision,reviewer,note,split='unassigned',trim_start_s=0.,trim_end_s=None):
 """Record an operator-supplied decision in a NEW manifest; no default approval."""
 import datetime,math
 target=Path(output)
 if target.exists():raise FileExistsError(target)
 if decision not in ('approved','failed','device_test','pending'):raise ValueError('Explicit human decision required')
 if not reviewer.strip() or not note.strip():raise ValueError('Named reviewer and review note required')
 if split not in ('unassigned','train','validation','test'):raise ValueError('Invalid split')
 if not math.isfinite(trim_start_s) or trim_start_s<0 or (trim_end_s is not None and (not math.isfinite(trim_end_s) or trim_end_s<=trim_start_s)):raise ValueError('Invalid trim')
 doc=json.loads(Path(manifest).read_text());matches=[e for e in doc['episodes'] if Path(e['episode']).resolve()==Path(episode).resolve()]
 if len(matches)!=1:raise ValueError('Choose exactly one episode in manifest')
 entry=matches[0]
 if fingerprint(entry['episode'])!=entry['fingerprints']:raise ValueError('Raw files changed since inventory')
 if decision=='approved':
  if not entry.get('complete') or not json.loads((Path(entry['episode'])/'episode.json').read_text()).get('complete'):raise ValueError('Incomplete episode cannot be approved')
  if split=='unassigned':raise ValueError('Approved episode requires explicit split')
  session=Path(entry['episode']).parent.name
  for other in doc['episodes']:
   if other is not entry and other.get('decision')=='approved' and Path(other['episode']).parent.name==session and other.get('split')!=split:raise ValueError('Split entire recording session; session overlap')
 entry.update(decision=decision,reviewer=reviewer.strip(),review_note=note.strip(),split=split,trim_start_s=trim_start_s,trim_end_s=trim_end_s,reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
 target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('x') as f:json.dump(doc,f,ensure_ascii=False,indent=2)
 return {'manifest':str(target),'episode':entry['episode'],'decision':decision,'formal_training_started':False}
