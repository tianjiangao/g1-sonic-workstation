"""Local-only fixtures; no robot, SSH, model or human approval of real episodes."""
import importlib,json,tempfile,unittest
from pathlib import Path
from sonic_pipeline.manifest import sha

class ReviewTests(unittest.TestCase):
 def test_review_writes_new_manifest_and_preserves_original(self):
  mod=importlib.import_module('sonic_pipeline.manifest')
  self.assertTrue(callable(getattr(mod,'record_review',None)),'Explicit review command is missing')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);ep=root/'SESSION_A/episode_0';ep.mkdir(parents=True)
   for name in ['context.json','frames.jsonl','events.jsonl']:(ep/name).write_text('{}')
   (ep/'episode.json').write_text('{"complete":true}')
   from sonic_pipeline.manifest import fingerprint
   entry={'episode':str(ep),'complete':True,'fingerprints':fingerprint(ep),'decision':'unreviewed','split':'unassigned','task':'fixture'}
   source=root/'review.json';source.write_text(json.dumps({'episodes':[entry]}));original=source.read_bytes()
   mod.record_review(source,root/'new.json',str(ep),'device_test','human','device test only','unassigned')
   self.assertEqual(source.read_bytes(),original)
   e=json.loads((root/'new.json').read_text())['episodes'][0]
   self.assertEqual(e['decision'],'device_test');self.assertEqual(e['reviewer'],'human')
   with self.assertRaises(FileExistsError):mod.record_review(source,root/'new.json',str(ep),'approved','human','ok','train')

class AcceptanceTests(unittest.TestCase):
 def module(self):
  spec=importlib.util.find_spec('sonic_pipeline.acceptance')
  self.assertIsNotNone(spec,'Accepted dataset receipt implementation is missing')
  return importlib.import_module('sonic_pipeline.acceptance')
 def fixture(self,root,engineering=True):
  root.mkdir();(root/'data').mkdir();(root/'data/example.parquet').write_bytes(b'acceptance unit fixture, not a real dataset')
  versions={'wbc_commit':'7f151314d4d1606544bf249d2a7a1cb754c64582','groot_commit':'51d4c89f72fda44cbf77285c6a8114b52676b8a1','wbc_files_sha256':{'gear_sonic/scripts/process_dataset.py':'a'*64},'groot_files_sha256':{'gr00t/data/types.py':'b'*64}}
  pro={'official_source_versions':versions,'schema':'sonic_token64_dex1x2_v1','engineering_only':engineering,'human_approved':not engineering,'official_cleaning':{'processor_sha256':'a'*64,'smpl_cleaning_disabled':True,'official_source_versions':versions},'episodes':[{'source_episode':'/fixture/SESSION_A/episode_0','source_session':'SESSION_A','review':{'decision':'engineering_only','reviewer':None,'review_note':None}}]}
  (root/'pipeline-provenance.json').write_text(json.dumps(pro))
  reader={'official_source_versions':versions,'actual_gr00t_reader':'PASS','full_numeric_scan':True,'full_video_decode':True,'artifact_sha256':{n:sha(root/n) for n in ['pipeline-provenance.json','data/example.parquet']}}
  (root/'reader-validation.json').write_text(json.dumps(reader));return pro
 def test_engineering_receipt_never_authorizes_formal_handoff(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'dataset';self.fixture(p);r=m.accept_dataset(p,engineering=True)
   self.assertTrue(r['engineering_only']);self.assertFalse(r['formal_training_eligible'])
   with self.assertRaisesRegex(ValueError,'Engineering|engineering'):m.verify_acceptance(p,engineering=False)
 def test_modified_provenance_and_extra_files_fail_after_acceptance(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'dataset';self.fixture(p);m.accept_dataset(p,engineering=True)
   (p/'extra.txt').write_text('unexpected')
   with self.assertRaisesRegex(ValueError,'changed|inventory'):m.verify_acceptance(p,engineering=True)
   (p/'extra.txt').unlink();(p/'pipeline-provenance.json').write_text('{}')
   with self.assertRaisesRegex(ValueError,'changed|hash'):m.verify_acceptance(p,engineering=True)
 def test_no_official_cleaning_cannot_be_accepted(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'dataset';pro=self.fixture(p);pro.pop('official_cleaning');(p/'pipeline-provenance.json').write_text(json.dumps(pro))
   with self.assertRaisesRegex(ValueError,'clean'):m.accept_dataset(p,engineering=True)
 def test_engineering_claim_cannot_upgrade_unreviewed_data(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'dataset';self.fixture(p)
   with self.assertRaisesRegex(ValueError,'Engineering|engineering|review'):m.accept_dataset(p,engineering=False)
 def test_symlink_is_rejected(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'dataset';self.fixture(p);(p/'data/link').symlink_to(p/'data/example.parquet')
   with self.assertRaisesRegex(ValueError,'symlink'):m.accept_dataset(p,engineering=True)
 def test_formal_boolean_flags_cannot_replace_human_review(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'dataset';self.fixture(p,engineering=False)
   with self.assertRaisesRegex(ValueError,'review'):m.accept_dataset(p)

 def test_wrong_recorded_official_commit_cannot_be_accepted(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'dataset';pro=self.fixture(p);pro['official_source_versions']['wbc_commit']='0'*40;(p/'pipeline-provenance.json').write_text(json.dumps(pro))
   reader=json.loads((p/'reader-validation.json').read_text());reader['artifact_sha256']['pipeline-provenance.json']=sha(p/'pipeline-provenance.json');(p/'reader-validation.json').write_text(json.dumps(reader))
   with self.assertRaisesRegex(ValueError,'source|version'):m.accept_dataset(p,engineering=True)

class FormalGateTests(unittest.TestCase):
 def test_formal_gate_requires_cleaning_acceptance(self):
  from sonic_pipeline.runner import gate
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for name,session in [('train','SESSION_A'),('val','SESSION_B')]:
    p=root/name;p.mkdir();(p/'data').write_bytes(b'fixture')
    (p/'pipeline-provenance.json').write_text(json.dumps({'schema':'sonic_token64_dex1x2_v1','engineering_only':False,'human_approved':True,'episodes':[{'source_episode':f'/raw/{session}/episode_0'}]}))
    (p/'reader-validation.json').write_text(json.dumps({'actual_gr00t_reader':'PASS','artifact_sha256':{'data':sha(p/'data')}}))
   with self.assertRaisesRegex(ValueError,'accept|clean'):gate(root/'train',root/'val')

class HandoffTests(unittest.TestCase):
 def test_unaccepted_dataset_cannot_reach_ssh(self):
  spec=importlib.util.find_spec('sonic_pipeline.upload_dataset');self.assertIsNotNone(spec,'Accepted-only SSH handoff is missing')
  m=importlib.import_module('sonic_pipeline.upload_dataset')
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises((ValueError,FileNotFoundError)):m.upload(Path(d),engineering=True)
 def test_remote_extractor_refuses_corruption_and_preserves_existing(self):
  spec=importlib.util.find_spec('sonic_pipeline.upload_dataset');self.assertIsNotNone(spec,'Verified atomic handoff is missing')
  import io,tarfile
  m=importlib.import_module('sonic_pipeline.upload_dataset')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);archive=root/'payload.tar'
   with tarfile.open(archive,'w') as t:
    item=tarfile.TarInfo('a');item.size=3;t.addfile(item,io.BytesIO(b'bad'))
   expected={'a':'0'*64}
   with archive.open('rb') as stream:
    with self.assertRaises(ValueError):m.receive_archive(stream,root/'dest',expected)
   self.assertFalse((root/'dest').exists())
   self.assertTrue(list(root.glob('.dest.partial-*')),'Failure evidence must remain recoverable')

if __name__=='__main__':unittest.main()

class CliTests(unittest.TestCase):
 def test_cli_exposes_local_and_accepted_only_handoff_commands(self):
  import subprocess,sys
  r=subprocess.run([sys.executable,'-m','sonic_pipeline.cli','--help'],text=True,capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr)
  for name in ['review-page','review','local-run','accept','upload']:self.assertIn(name,r.stdout)
 def test_raw_sync_cannot_bypass_local_acceptance(self):
  from sonic_pipeline.sync_raw import sync
  with self.assertRaisesRegex(ValueError,'accept|验收'):sync()

class FormalReceiptTests(AcceptanceTests):
 def formal_fixture(self,path,split,session):
  pro=self.fixture(path,engineering=False)
  e=pro['episodes'][0];e.update(source_episode=f'/fixture/{session}/episode_0',source_session=session,split=split,raw_sha256={n:__import__('hashlib').sha256((session+n).encode()).hexdigest() for n in ['episode.json','context.json','frames.jsonl','events.jsonl']},trim_start_s=0.,trim_end_s=None,review={'decision':'approved','reviewer':'unit-test-fixture','review_note':'synthetic receipt contract test'})
  (path/'pipeline-provenance.json').write_text(json.dumps(pro))
  snapshot={'episodes':[{'episode':e['source_episode'],'fingerprints':e['raw_sha256'],'decision':'approved','reviewer':'unit-test-fixture','review_note':'synthetic receipt contract test','split':split,'trim_start_s':0.,'trim_end_s':None}]}
  (path/'human-review.json').write_text(json.dumps(snapshot))
  r=json.loads((path/'reader-validation.json').read_text());r['artifact_sha256'].update({n:sha(path/n) for n in ['pipeline-provenance.json','human-review.json']});(path/'reader-validation.json').write_text(json.dumps(r))
 def test_complete_formal_receipts_pass_for_distinct_sessions(self):
  m=self.module()
  from sonic_pipeline.runner import gate
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a=root/'train';b=root/'validation'
   self.formal_fixture(a,'train','SESSION_T');self.formal_fixture(b,'validation','SESSION_V')
   m.accept_dataset(a);m.accept_dataset(b)
   self.assertFalse(gate(a,b)['engineering_only'])
 def test_same_session_at_different_source_roots_is_rejected(self):
  m=self.module()
  from sonic_pipeline.runner import gate
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a=root/'train';b=root/'validation'
   self.formal_fixture(a,'train','SESSION_DUP');self.formal_fixture(b,'validation','SESSION_DUP')
   pro=json.loads((b/'pipeline-provenance.json').read_text());pro['episodes'][0]['source_episode']='/another-root/SESSION_DUP/episode_0';(b/'pipeline-provenance.json').write_text(json.dumps(pro))
   snap=json.loads((b/'human-review.json').read_text());snap['episodes'][0]['episode']='/another-root/SESSION_DUP/episode_0';(b/'human-review.json').write_text(json.dumps(snap))
   r=json.loads((b/'reader-validation.json').read_text());r['artifact_sha256'].update({n:sha(b/n) for n in ['pipeline-provenance.json','human-review.json']});(b/'reader-validation.json').write_text(json.dumps(r))
   m.accept_dataset(a);m.accept_dataset(b)
   with self.assertRaisesRegex(ValueError,'session overlap'):gate(a,b)
 def test_training_and_validation_must_respect_reviewed_roles(self):
  m=self.module()
  from sonic_pipeline.runner import gate
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a=root/'train';b=root/'validation'
   self.formal_fixture(a,'test','SESSION_T');self.formal_fixture(b,'train','SESSION_V')
   m.accept_dataset(a);m.accept_dataset(b)
   with self.assertRaisesRegex(ValueError,'split|role'):gate(a,b)
 def test_copied_raw_episode_with_renamed_session_is_rejected(self):
  m=self.module()
  from sonic_pipeline.runner import gate
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a=root/'train';b=root/'validation'
   self.formal_fixture(a,'train','SESSION_T');self.formal_fixture(b,'validation','RENAMED_SESSION')
   pro=json.loads((b/'pipeline-provenance.json').read_text());source=json.loads((a/'pipeline-provenance.json').read_text())['episodes'][0]['raw_sha256'];pro['episodes'][0]['raw_sha256']=source;(b/'pipeline-provenance.json').write_text(json.dumps(pro))
   snap=json.loads((b/'human-review.json').read_text());snap['episodes'][0]['fingerprints']=source;(b/'human-review.json').write_text(json.dumps(snap))
   r=json.loads((b/'reader-validation.json').read_text());r['artifact_sha256'].update({n:sha(b/n) for n in ['pipeline-provenance.json','human-review.json']});(b/'reader-validation.json').write_text(json.dumps(r))
   m.accept_dataset(a);m.accept_dataset(b)
   with self.assertRaisesRegex(ValueError,'raw.*overlap|content.*overlap'):gate(a,b)

class SourceAndPathTests(unittest.TestCase):
 def test_engineering_and_formal_output_roots_are_distinct(self):
  from unittest.mock import patch
  import sonic_pipeline.policy_guard as m
  self.assertTrue(callable(getattr(m,'check_processing_output',None)),'Mode-aware local output guard missing')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);contract={'local_processing':{'root':d,'datasets':str(root/'datasets'),'engineering_reports':str(root/'reports')}}
   with patch.object(m,'HOME',root),patch.object(m,'check_policy',return_value=contract):
    m.check_processing_output(root/'reports/run',True);m.check_processing_output(root/'datasets/task',False)
    with self.assertRaises(ValueError):m.check_processing_output(root/'datasets/run',True)
    with self.assertRaises(ValueError):m.check_processing_output(root/'reports/task',False)
 def test_pinned_data_source_edit_is_rejected_but_unrelated_patch_is_preserved(self):
  import sonic_pipeline.policy_guard as m
  self.assertTrue(callable(getattr(m,'check_pinned_files',None)),'Pinned official source verification missing')
  import subprocess
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   def git(*args):return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL,text=True).strip()
   git('init','-q');(root/'processor.py').write_text('official');(root/'controller.txt').write_text('existing controller');git('add','.');git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture');revision=git('rev-parse','HEAD')
   (root/'controller.txt').write_text('approved unrelated patch')
   self.assertIn('processor.py',m.check_pinned_files(root,revision,['processor.py']))
   (root/'processor.py').write_text('unreviewed processor')
   with self.assertRaisesRegex(ValueError,'source|changed'):m.check_pinned_files(root,revision,['processor.py'])

class HandoffReuseTests(unittest.TestCase):
 def test_verified_remote_bytes_can_be_reused_without_mutating_old_package(self):
  import inspect,tarfile
  from sonic_pipeline.upload_dataset import receive_archive
  self.assertIn('reusable',inspect.signature(receive_archive).parameters,'Verified remote reuse is missing')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);seed=root/'old-package';seed.mkdir();(seed/'a').write_bytes(b'verified')
   expected={'a':sha(seed/'a')};archive=root/'empty.tar'
   with tarfile.open(archive,'w'):pass
   with archive.open('rb') as f:r=receive_archive(f,root/'new-package',expected,{'a':str(seed/'a')})
   self.assertEqual((root/'new-package/a').read_bytes(),b'verified');self.assertEqual((seed/'a').read_bytes(),b'verified');self.assertEqual(r['remote_hash_verification'],'PASS')
 def test_bad_remote_reuse_cannot_publish(self):
  import inspect,tarfile
  from sonic_pipeline.upload_dataset import receive_archive
  self.assertIn('reusable',inspect.signature(receive_archive).parameters,'Verified remote reuse is missing')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'bad').write_bytes(b'corrupt');archive=root/'empty.tar'
   with tarfile.open(archive,'w'):pass
   with archive.open('rb') as f:
    with self.assertRaises(ValueError):receive_archive(f,root/'new-package',{'a':'0'*64},{'a':str(root/'bad')})
   self.assertFalse((root/'new-package').exists())
 def test_reuse_probe_rejects_namespace_symlink_outside_approved_root(self):
  import inspect
  from sonic_pipeline.upload_dataset import reusable_files
  self.assertIn('approved_root',inspect.signature(reusable_files).parameters,'Reuse probe must check fixed root before reading')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);approved=root/'approved';approved.mkdir();outside=root/'outside';outside.mkdir();(approved/'engineering').symlink_to(outside)
   with self.assertRaisesRegex(ValueError,'approved root'):reusable_files(approved/'engineering/new',{},approved)
