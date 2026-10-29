"""Run with pinned GR00T Python; all generated data is temporary and synthetic."""
import tempfile,unittest,json,subprocess
from pathlib import Path
import numpy as np,pyarrow as pa,pyarrow.parquet as pq
from sonic_pipeline.validate_dataset import scan_parquet,scan_video

class FullScanTests(unittest.TestCase):
 def write(self,p,corrupt=None):
  n=61;d={'timestamp':np.arange(n)/50,'task_index':[0]*n}
  for key,width in [('observation.body',29),('observation.dex1',2),('observation.projected_gravity',3),('action.motion_token',64),('action.dex1',2)]:d[key]=[[0.]*width for _ in range(n)]
  if corrupt=='nan':d['action.motion_token'][11][13]=float('nan')
  if corrupt=='time':d['timestamp'][11]=d['timestamp'][10]
  pq.write_table(pa.table(d),p)
 def test_finite_columns_return_exact_count(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'data.parquet';self.write(p);n,tasks=scan_parquet(p);self.assertEqual(n,61);self.assertEqual(tasks,{0})
 def test_nan_away_from_reader_sample_windows_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'data.parquet';self.write(p,'nan')
   with self.assertRaisesRegex(ValueError,'column'):scan_parquet(p)
 def test_duplicate_timestamp_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'data.parquet';self.write(p,'time')
   with self.assertRaisesRegex(ValueError,'timestamps'):scan_parquet(p)
 def test_video_count_mismatch_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'fixture.mp4'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=640x480:r=50','-frames:v','41','-c:v','libx264','-threads','1',str(p)],check=True)
   self.assertEqual(scan_video(p,41)['frames'],41)
   with self.assertRaisesRegex(ValueError,'mismatch'):scan_video(p,42)
if __name__=='__main__':unittest.main()

class OriginTests(FullScanTests):
 def test_shifted_table_time_origin_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'data.parquet';self.write(p);t=pq.read_table(p);t=t.set_column(t.schema.get_field_index('timestamp'),'timestamp',pa.array(np.arange(61)/50+1));pq.write_table(t,p)
   with self.assertRaisesRegex(ValueError,'origin|timestamps'):scan_parquet(p)
 def test_shifted_video_time_origin_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'fixture.mp4'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=640x480:r=50','-frames:v','41','-c:v','libx264','-threads','1','-output_ts_offset','2',str(p)],check=True)
   with self.assertRaisesRegex(ValueError,'origin|PTS'):scan_video(p,41)
