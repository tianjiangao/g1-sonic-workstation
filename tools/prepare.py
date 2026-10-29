#!/usr/bin/env python3
"""Install source overlays into a CLEAN pinned checkout. Default: read-only plan.
Never installs packages, fetches weights, writes a policy lock or starts a service.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

RELEASE=Path(__file__).resolve().parents[1]

def safe_path(value):
    p=Path(value).expanduser().absolute()
    if not re.fullmatch(r'[\w/. -]+',str(p)):
        raise ValueError('Choose a path without shell metacharacters')
    return p

def require_new(p):
    if p.exists() or p.is_symlink():raise FileExistsError('Choose a NEW workspace: '+str(p))

def require_overlay_absent(wbc):
    for name in ['official_sonic','offline_replay','sim_teleop']:
        p=wbc/name
        if p.exists() or p.is_symlink():raise FileExistsError('Existing overlay; preserve it: '+str(p))

def git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()

def check_revision(repo,revision):
    if git(repo,'rev-parse','HEAD')!=revision:raise ValueError('Pinned revision mismatch: '+str(repo))

def relocate(text,workspace,wbc,groot,audio):
    for old,new in [('/opt/g1/GR00T-WholeBodyControl',wbc),('/opt/g1/Isaac-GR00T',groot),('/opt/g1/audio-env',audio),('/opt/g1/workspace',workspace)]:text=text.replace(old,str(new))
    return text

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['wbc','workspace','groot','audio-env']:p.add_argument('--'+name,required=True,type=safe_path)
    p.add_argument('--apply',action='store_true',help='Apply reviewed patch and copy overlay; never overwrite existing content')
    a=p.parse_args();versions=json.loads((RELEASE/'references/versions.json').read_text())
    require_new(a.workspace);require_overlay_absent(a.wbc)
    check_revision(a.wbc,versions['wbc_commit']);check_revision(a.groot,versions['groot_commit'])
    if git(a.wbc,'status','--porcelain','--untracked-files=normal'):raise ValueError('WBC checkout must be clean; use a separate clone')
    if any(x in str(a.workspace) for x in ["'",'"','\n']):raise ValueError('Unsupported workspace path')
    patch=RELEASE/'patches/wbc-local-fixes.patch'
    subprocess.run(['git','-C',str(a.wbc),'apply','--check',str(patch)],check=True)
    entries=[]
    for source in sorted((RELEASE/'wbc').rglob('*')):
        if source.is_file() and '__pycache__' not in source.parts:
            target=a.wbc/source.relative_to(RELEASE/'wbc')
            if target.exists() or target.is_symlink():raise FileExistsError('Overlay would overwrite: '+str(target))
            entries.append((source,target))
    for name in ['capture','sonic_pipeline']:
        entries += [(s,a.workspace/s.relative_to(RELEASE)) for s in (RELEASE/name).rglob('*') if s.is_file() and '__pycache__' not in s.parts]
    entries += [(RELEASE/'pipeline.sh',a.workspace/'pipeline.sh')]
    plan={'apply':a.apply,'workspace':str(a.workspace),'wbc':str(a.wbc),'files':len(entries),'patch':str(patch),'robot_started':False,'policy_provisioned':False}
    print(json.dumps(plan,indent=2))
    if not a.apply:return
    # All destinations and the upstream patch were checked before any mutation.
    a.workspace.mkdir(parents=True,exist_ok=False)
    journal=a.workspace/'installation.json';journal.write_text(json.dumps(dict(plan,status='in_progress'),indent=2))
    for source,target in entries:
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('x') as f:f.write(relocate(source.read_text(),a.workspace,a.wbc,a.groot,a.audio_env))
        target.chmod(source.stat().st_mode & 0o777)
    subprocess.run(['git','-C',str(a.wbc),'apply',str(patch)],check=True)
    journal.write_text(json.dumps(dict(plan,status='source_installed',formal_pipeline='blocked_until_site_policy_review'),indent=2))
    print('Source installed. Review docs/SETUP.zh-CN.md before configuring or starting hardware.')
if __name__=='__main__':main()
