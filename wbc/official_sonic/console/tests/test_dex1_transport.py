import unittest
from unittest.mock import patch
from unitree_sdk2py.core import channel
from official_sonic.dex1_transport import initialize
class Dex1TransportTests(unittest.TestCase):
 def test_sdk_transport_is_scoped_and_body_defaults_restored(self):
  original=channel.ChannelConfigHasInterface;seen=[]
  with patch.object(channel,'ChannelFactoryInitialize',side_effect=lambda d,n:seen.append((d,n,channel.ChannelConfigHasInterface))):result=initialize('enp4s0')
  self.assertIn('<AllowMulticast>spdp</AllowMulticast>',seen[0][2]);self.assertEqual(seen[0][:2],(0,'enp4s0'));self.assertEqual(channel.ChannelConfigHasInterface,original);self.assertFalse(result['sdk_files_modified'])
 def test_failed_initialization_restores_sdk_defaults(self):
  original=channel.ChannelConfigHasInterface
  with patch.object(channel,'ChannelFactoryInitialize',side_effect=RuntimeError('network unavailable')):
   with self.assertRaises(RuntimeError):initialize('absent')
  self.assertEqual(channel.ChannelConfigHasInterface,original)
