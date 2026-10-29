"""Resume pinned public NVIDIA weights using validated HTTP ranges + final SHA256.

No executable files are fetched/run. Existing HF partial files are retained.
"""
import concurrent.futures,hashlib,json,os,time
from pathlib import Path
import requests
from sonic_pipeline.settings import BASE_REPO,BASE_REVISION,BASE_PATH,ROOT
FILES={'model-00001-of-00002.safetensors':(4990519232,'8a1a1d8a33c99103c7c80c136073c5bb8bfe9ca8f7a970c93c033ea89742906d'),'model-00002-of-00002.safetensors':(1919980184,'c3f61940deb2007ba1ad7743013b57f0f8462356151db9655175d7aca2d40661')}
CHUNK=32*1024*1024

def main():
 cache=BASE_PATH.parents[1];parts=ROOT/'downloads';parts.mkdir(exist_ok=True);jobs=[];complete=0
 for name,(size,digest) in FILES.items():
  blob=cache/'blobs'/digest
  if blob.exists() and blob.stat().st_size==size:continue
  folder=parts/digest;folder.mkdir(exist_ok=True);old=blob.with_suffix('.incomplete')
  for start in range(0,size,CHUNK):
   end=min(start+CHUNK,size);target=folder/f'{start:012d}.part'
   if not target.exists() and old.exists() and old.stat().st_size>=end:
    with old.open('rb') as f:f.seek(start);target.write_bytes(f.read(end-start))
   if target.exists() and target.stat().st_size==end-start:complete+=end-start;continue
   jobs.append((name,start,end,target,size))
 print(json.dumps({'verified_range_download':True,'queued_parts':len(jobs),'resumed_bytes':complete}),flush=True)
 def fetch(job):
  name,start,end,target,size=job;url=f'https://huggingface.co/{BASE_REPO}/resolve/{BASE_REVISION}/{name}'
  for attempt in range(4):
   tmp=target.with_suffix('.tmp')
   try:
    with requests.get(url,headers={'Range':f'bytes={start}-{end-1}','Accept-Encoding':'identity'},stream=True,timeout=(20,60)) as r:
     if r.status_code!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end-1}/{size}':raise RuntimeError('HTTP range was not respected')
     with tmp.open('wb') as f:
      for chunk in r.iter_content(1024*1024):f.write(chunk)
    if tmp.stat().st_size!=end-start:raise RuntimeError('Incomplete range')
    tmp.replace(target);return end-start
   except Exception:
    if attempt==3:raise
    time.sleep(attempt+1)
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  count=0
  for task in concurrent.futures.as_completed([pool.submit(fetch,j) for j in jobs]):
   complete+=task.result();count+=1
   if count%4==0:print(json.dumps({'parts_completed':count,'bytes_completed_or_resumed':complete}),flush=True)
 results=[]
 for name,(size,digest) in FILES.items():
  blob=cache/'blobs'/digest
  if not blob.exists():
   tmp=parts/(digest+'.assembled');h=hashlib.sha256()
   with tmp.open('wb') as out:
    for start in range(0,size,CHUNK):
     with (parts/digest/f'{start:012d}.part').open('rb') as f:
      for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk);out.write(chunk)
   if tmp.stat().st_size!=size or h.hexdigest()!=digest:raise RuntimeError('Model weight SHA256 mismatch')
   tmp.replace(blob)
  else:
   h=hashlib.sha256()
   with blob.open('rb') as f:
    for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
   if h.hexdigest()!=digest:raise RuntimeError('Cached weight SHA256 mismatch')
  link=BASE_PATH/name
  if not link.exists():link.symlink_to(Path('../../blobs')/digest)
  results.append({'name':name,'size':size,'sha256':digest})
 record={'repo':BASE_REPO,'revision':BASE_REVISION,'path':str(BASE_PATH),'download_complete':True,'weight_sha256_verified':results}
 (ROOT/'base-model.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
if __name__=='__main__':main()
