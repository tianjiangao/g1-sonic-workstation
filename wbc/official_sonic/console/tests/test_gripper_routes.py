import unittest
from official_sonic.dex1_mapping import load_routes

class GripperRouteTests(unittest.TestCase):
 def test_default_is_verified_robot_physical_sides(self):
  self.assertEqual(load_routes(),{'left':'right','right':'left'})
 def test_both_sides_must_not_alias_same_motor(self):
  import json,tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.json';p.write_text(json.dumps({'physical_to_wire':{'left':'left','right':'left'}}))
   with self.assertRaises(ValueError):load_routes(p)
