"""Build a data-free, credential-free cloud deployment artifact."""
import json,shutil,subprocess
from pathlib import Path
from sonic_pipeline.settings import ROOT,HOME,GROOT,WBC,BASE_REPO,BASE_REVISION
from sonic_pipeline.manifest import sha

def bundle(output):
 out=Path(output).resolve()
 if out.exists():raise FileExistsError(out)
 # Tracked source modifications would make the archived version misleading.
 if subprocess.run(['git','diff','--quiet','HEAD'],cwd=GROOT).returncode:raise ValueError('Isaac-GR00T tracked files changed; review before packaging')
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=GROOT,text=True).strip();out.mkdir(parents=True)
 pkg=out/'sonic_pipeline';pkg.mkdir();(pkg/'cloud').mkdir()
 for p in ROOT.glob('*.py'):shutil.copy2(p,pkg/p.name)
 for p in (ROOT/'cloud').iterdir():
  if p.is_file():shutil.copy2(p,pkg/'cloud'/p.name)
 shutil.copy2(HOME/'pipeline.sh',out/'pipeline.sh')
 shutil.copy2(HOME/'AGENTS.md',out/'AGENTS.md');(out/'agent.md').symlink_to('AGENTS.md')
 for name in ['workflow-contract.json','policy-lock.json']:shutil.copy2(ROOT/name,pkg/name)
 subprocess.run(['git','archive','--format=tar','--output',str(out/'Isaac-GR00T-source.tar'),'HEAD','gr00t','pyproject.toml','uv.lock','README.md','LICENSE','scripts'],cwd=GROOT,check=True)
 record={'groot_repo':'https://github.com/NVIDIA/Isaac-GR00T','groot_commit':commit,'groot_source_archive_sha256':sha(out/'Isaac-GR00T-source.tar'),'wbc_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=WBC,text=True).strip(),'base_model':BASE_REPO,'base_revision':BASE_REVISION,'profile':'8xL40','data_included':False,'credentials_included':False,'uploaded':False,'cloud_execution_verified':False}
 (out/'deployment-lock.json').write_text(json.dumps(record,indent=2));files=sorted(p for p in out.rglob('*') if p.is_file())
 (out/'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(out))+'\n' for p in files))
 return dict(record,output=str(out),files=len(files))
