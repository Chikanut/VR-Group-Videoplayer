import unittest
from unittest.mock import patch

from App.server import device_discovery


class DeviceDiscoverySubnetTests(unittest.TestCase):
    @patch("App.server.device_discovery.socket.socket")
    def test_detect_subnet_prefers_route_ip(self, mock_socket_cls):
        mock_socket = mock_socket_cls.return_value
        mock_socket.getsockname.return_value = ("192.168.50.12", 12345)

        subnet = device_discovery.detect_subnet()

        self.assertEqual(subnet, "192.168.50")

    @patch("App.server.device_discovery.socket.socket")
    def test_detect_subnet_falls_back_to_default(self, mock_socket_cls):
        mock_socket = mock_socket_cls.return_value
        mock_socket.connect.side_effect = OSError("no route")

        subnet = device_discovery.detect_subnet()

        self.assertEqual(subnet, "192.168.1")


if __name__ == "__main__":
    unittest.main()
