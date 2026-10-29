import unittest
from sim_teleop.safety import assert_isolated, validate_network

class SafetyTests(unittest.TestCase):
    def test_host_rejected(self):
        with self.assertRaises(RuntimeError):
            assert_isolated()
    def test_physical_interface_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_network('net:[2]', 'net:[1]', ['lo','enp4s0'], '')
    def test_route_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_network('net:[2]', 'net:[1]', ['lo'], 'default via 1.2.3.4')
    def test_same_namespace_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_network('net:[1]', 'net:[1]', ['lo'], '')
    def test_private_loopback_accepted(self):
        validate_network('net:[2]', 'net:[1]', ['lo'], '')

if __name__ == '__main__': unittest.main()
