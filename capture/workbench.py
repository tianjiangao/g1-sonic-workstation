"""Offline episode inventory and structural diagnostics; no robot imports or approval."""
import json,math,hashlib
from collections import defaultdict
from pathlib import Path
from capture.core import REQUIRED

def _jsonlines(path):
    with path.open() as source:
        for line in source:
            if line.strip():yield json.loads(line)

def catalog(root):
    rows=[]
    for p in sorted(Path(root).glob('SESSION_*/episode_*/episode.json')):
        m=json.loads(p.read_text());ep=p.parent
        context=json.loads((ep/'context.json').read_text()) if (ep/'context.json').exists() else {}
        session=context.get('session',{});fps=session.get('fps',15)
        rows.append({'episode':str(ep),'id':hashlib.sha256(str(ep.resolve()).encode()).hexdigest()[:16],
            'number':m.get('take_number'),'batch':m.get('batch_id','legacy'),'frames':m.get('frames',0),
            'duration_s':m.get('frames',0)/fps,'complete':m.get('complete',False),'task':session.get('task',''),
            'decision':'pending'})
    return rows

def quality(episode):
    ep=Path(episode).resolve();meta=json.loads((ep/'episode.json').read_text())
    errors=[];ages=defaultdict(list);times=[];seen=defaultdict(set);ranges=defaultdict(list);tokens=0;token_invalid=0
    frames=0;missing_streams=set()
    for f in _jsonlines(ep/'frames.jsonl'):
        frames+=1;t=f['mono_ns'];times.append(t)
        for key,n in [('observation.body',29),('action.body',29),('observation.dex1',2),('action.dex1',2)]:
            values=f.get(key,[])
            if len(values)!=n or not all(type(x) in (float,int) and math.isfinite(x) for x in values):errors.append('invalid '+key)
            if n==2:
                for i,side in enumerate(('left','right')):
                    if len(values)==n:ranges[key+'.'+side].append(values[i])
        receipts=f.get('source_receipts',{})
        for key in REQUIRED:
            if key not in receipts:missing_streams.add(key);continue
            age=(t-receipts[key]['mono_ns'])/1e9;ages[key].append(age)
            limit=30 if key=='robot_config' else .5 if key.startswith('camera_') else .25
            if not 0<=age<=limit:errors.append('future/stale '+key)
        for role,relative in f.get('images',{}).items():
            p=(ep/relative).resolve()
            if not p.is_relative_to(ep) or not p.is_file():errors.append('missing/unsafe camera '+role)
            seen[role].add(relative)
        if set(f.get('images',{}))!={'ego_view','left_wrist','right_wrist'}:errors.append('missing camera role')
    if times and any(b<=a for a,b in zip(times,times[1:])):errors.append('nonmonotonic frame time')
    if frames!=meta.get('frames'):errors.append('frame count mismatch')
    if not frames or not meta.get('complete'):errors.append('empty/incomplete episode')
    events=defaultdict(int)
    for e in _jsonlines(ep/'events.jsonl'):
        topic=e.get('topic');events[topic]+=1
        if topic=='g1_debug':
            token=e.get('data',{}).get('token_state',[])
            if len(token)==64 and all(type(x) in (int,float) and math.isfinite(x) for x in token):tokens+=1
            else:token_invalid+=1
    if not tokens or token_invalid:errors.append('missing/invalid raw 64D SONIC token')
    for key in REQUIRED:
        if not events.get(key) and key!='robot_config':missing_streams.add(key)
    if missing_streams:errors.append('missing streams: '+','.join(sorted(missing_streams)))
    def stats(values):
        s=sorted(values);return {'p95_ms':s[min(len(s)-1,int((len(s)-1)*.95))]*1000,'max_ms':max(s)*1000}
    warnings=['constant Dex1 command: '+side for side in ('left','right') if ranges['action.dex1.'+side] and max(ranges['action.dex1.'+side])-min(ranges['action.dex1.'+side])<1e-6]
    return {'warnings':warnings,'schema':'workstation-quality-v1','episode':str(ep),'result':'PASS_STRUCTURAL' if not errors else 'FAIL',
        'errors':sorted(set(errors)),'frames':frames,'duration_s':(times[-1]-times[0])/1e9 if len(times)>1 else 0,
        'max_frame_gap_ms':max([(b-a)/1e6 for a,b in zip(times,times[1:])],default=0),
        'receipt_age':{k:stats(v) for k,v in ages.items()},'event_counts':dict(events),'valid_64d_token_events':tokens,
        'dex1_ranges':{k:{'min':min(v),'max':max(v)} for k,v in ranges.items() if v},
        'unique_camera_frames':{k:len(v) for k,v in seen.items()},'human_review':'pending',
        'sensor_clocks_synchronized':False,'training_ready':False,
        'limitations':['Reception age is not sensor exposure synchronization.','Structural integrity is not task success, official cleaning, or Isaac-GR00T reader acceptance.']}
