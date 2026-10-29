"""Offline original-frame review; never records or infers an approval decision."""
import json,html,shutil
from pathlib import Path
from sonic_pipeline.manifest import fingerprint,sha

def build_review_page(manifest,output):
 target=Path(output)
 if target.exists():raise FileExistsError(target)
 doc=json.loads(Path(manifest).read_text());rows=[]
 for entry in doc['episodes']:
  ep=Path(entry['episode'])
  if fingerprint(ep)!=entry['fingerprints']:raise ValueError('Raw files changed since review inventory')
  frames=[json.loads(line) for line in (ep/'frames.jsonl').read_text().splitlines() if line.strip()]
  rows.append({'take':entry.get('take',entry.get('number')),'episode':str(ep),'task':entry['task'],'decision':entry['decision'],'complete':entry['complete'],'frames':frames})
 target.mkdir(parents=True);media=target/'images';media.mkdir()
 for row in rows:
  for frame in row['frames']:
   refs={}
   for role,relative in frame['images'].items():
    source=(Path(row['episode'])/relative).resolve()
    if not source.is_relative_to(Path(row['episode']).resolve()) or source.is_symlink():raise ValueError('Unsafe review image')
    digest=sha(source);dest=media/(digest+'.jpg')
    if not dest.exists():shutil.copy2(source,dest)
    refs[role]='images/'+digest+'.jpg'
   frame['images']=refs
 # Snapshot of the decisions at generation; this page cannot mutate the manifest.
 (target/'review-snapshot.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2))
 payload=json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')
 page=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SONIC 本机人工回放</title>
<style>*{box-sizing:border-box}body{font:16px/1.55 system-ui,sans-serif;max-width:1320px;margin:0 auto;padding:32px;background:#f4f7f8;color:#172b40}h1{font-size:30px;letter-spacing:-.04em;margin:0 0 8px}p{color:#526575}select,button,input{font:inherit;padding:10px;border:1px solid #cbd5dc;border-radius:7px}select{display:block;width:100%;margin:20px 0 12px;background:white}button{background:#0f766e;color:white;border-color:#0f766e;font-weight:600}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #0f766e;outline-offset:3px}input{width:70%;vertical-align:middle}#views{display:grid;grid-template-columns:2fr 1fr 1fr;gap:14px}figure{margin:0;background:white;padding:12px;border:1px solid #dce3e7;border-radius:10px}figcaption{font-weight:600;margin-bottom:8px}img{width:100%;height:260px;object-fit:contain;background:#eef2f4;border-radius:5px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace;background:white;border:1px solid #dce3e7;padding:16px;border-radius:8px}p:last-of-type{font-size:14px}@media(max-width:760px){body{padding:18px}#views{grid-template-columns:1fr}img{height:240px}input{width:60%}}</style>
<h1>SONIC 本机人工回放</h1><p>此页只回放已保存原始帧，不连接机器人，不自动判断成功。画面顺序：头部、物理左腕、物理右腕；头部保留原始双目。</p>
<select id="episode"></select><button id="play">播放 / 暂停</button><input id="frame" type="range" min="0" value="0"><pre id="info"></pre>
<div id="views"><figure><figcaption>头部双目</figcaption><img id="ego_view"></figure><figure><figcaption>物理左腕</figcaption><img id="left_wrist"></figure><figure><figcaption>物理右腕</figcaption><img id="right_wrist"></figure></div>
<p>人工决定请用 pipeline.sh review 命令写入一个新清单。approved 必须明确审核人、成功依据和整个 session 的 split。试录保持 device_test / pending / unreviewed。</p>
<script>const rows=PAYLOAD;const ep=document.getElementById('episode'),slider=document.getElementById('frame');let timer=null;
rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent='第 '+r.take+' 段 · '+r.task+' · 待人工审核';ep.append(o)});
function show(){const r=rows[Number(ep.value)],f=r.frames[Number(slider.value)];if(!f)return;['ego_view','left_wrist','right_wrist'].forEach(k=>document.getElementById(k).src=f.images[k]);document.getElementById('info').textContent=r.task+' | '+r.decision+' | complete='+r.complete+' | 帧 '+(Number(slider.value)+1)+'/'+r.frames.length+' | 接收时间 '+((f.mono_ns-r.frames[0].mono_ns)/1e9).toFixed(3)+'s\n'+r.episode+'\nDex1观测 '+JSON.stringify(f['observation.dex1'])+' / 命令 '+JSON.stringify(f['action.dex1']);}
ep.onchange=()=>{slider.max=Math.max(0,rows[Number(ep.value)].frames.length-1);slider.value=0;show()};slider.oninput=show;document.getElementById('play').onclick=()=>{if(timer){clearTimeout(timer);timer=null;return}function tick(){if(Number(slider.value)>=Number(slider.max)){timer=null;return}const r=rows[Number(ep.value)],i=Number(slider.value),delay=Math.max(1,(r.frames[i+1].mono_ns-r.frames[i].mono_ns)/1e6);timer=setTimeout(()=>{slider.value=i+1;show();tick()},delay)}tick()};if(rows.length)ep.onchange();</script></html>'''.replace('PAYLOAD',payload)
 (target/'index.html').write_text(page)
 return {'review_page':str((target/'index.html').resolve()),'episodes':len(rows),'decisions_changed':False}
