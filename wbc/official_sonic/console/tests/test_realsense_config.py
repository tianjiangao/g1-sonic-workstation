"""Test the real upstream factory method; replace only hardware SDK boundaries."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from official_sonic.console.backend import ROOT

def factory():
    tree=ast.parse((ROOT/'gear_sonic/camera/composed_camera.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ComposedCameraSensor')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_instantiate_camera')
    ns={'Sensor':object};exec(compile(ast.Module(body=[method],type_ignores=[]),'upstream_camera_factory','exec'),ns)
    return ns['_instantiate_camera']

class CameraConfigTests(unittest.TestCase):
    def setUp(self):
        self.ctor=Mock(return_value=object())
        self.driver=SimpleNamespace(RealSenseSensor=self.ctor,RealSenseConfig=SimpleNamespace)
        self.sdk=SimpleNamespace(camera_info=SimpleNamespace(serial_number='serial'),
            context=lambda:SimpleNamespace(query_devices=lambda:[SimpleNamespace(get_info=lambda _:s) for s in []]))
        self.owner=SimpleNamespace(config=SimpleNamespace(fps=15))
    def invoke(self,serial,enumerated=('3720','1015')):
        self.sdk.context=lambda:SimpleNamespace(query_devices=lambda:[SimpleNamespace(get_info=lambda _,s=s:s) for s in enumerated])
        with patch.dict(sys.modules,{'pyrealsense2':self.sdk,'gear_sonic.camera.drivers.realsense':self.driver}):
            return factory()(self.owner,'left_wrist','realsense',serial)
    def test_explicit_serial_uses_sorted_driver_index_and_passes_fps(self):
        self.invoke('3720');kw=self.ctor.call_args.kwargs
        self.assertEqual(kw['id'],1);self.assertEqual(kw['config'].fps,15)
        self.assertEqual(kw['mount_position'],'left_wrist')
    def test_usb_enumeration_reordering_keeps_same_selection(self):
        self.invoke('1015');first=self.ctor.call_args.kwargs['id']
        self.invoke('1015',('1015','3720'));self.assertEqual(first,self.ctor.call_args.kwargs['id'])
    def test_missing_serial_does_not_open_wrong_device(self):
        for serial in [None,'unknown']:
            with self.subTest(serial=serial),self.assertRaises(ValueError):self.invoke(serial)
        self.ctor.assert_not_called()

if __name__=='__main__':unittest.main()
