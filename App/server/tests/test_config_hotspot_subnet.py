import unittest
from unittest.mock import patch

from App.server import config


class AndroidHotspotSubnetDetectionTests(unittest.TestCase):
    @patch.dict("App.server.config.os.environ", {}, clear=True)
    @patch("App.server.config.socket.socket")
    def test_prefers_route_detected_ip_subnet(self, mock_socket_cls):
        mock_socket = mock_socket_cls.return_value.__enter__.return_value
        mock_socket.getsockname.return_value = ("192.168.50.12", 12345)

        subnet, source = config._detect_android_hotspot_subnet_with_source()

        self.assertEqual(subnet, "192.168.50")
        self.assertEqual(source, "route")

    @patch.dict("App.server.config.os.environ", {}, clear=True)
    @patch("App.server.config.socket.gethostbyname_ex", return_value=("host", [], ["10.0.0.77"]))
    @patch("App.server.config.socket.gethostname", return_value="host")
    @patch("App.server.config.socket.socket")
    def test_falls_back_to_hostname_when_route_unavailable(
        self,
        mock_socket_cls,
        _mock_gethostname,
        _mock_gethostbyname_ex,
    ):
        mock_socket = mock_socket_cls.return_value.__enter__.return_value
        mock_socket.connect.side_effect = OSError("no route")

        subnet, source = config._detect_android_hotspot_subnet_with_source()

        self.assertEqual(subnet, "10.0.0")
        self.assertEqual(source, "hostname")

    @patch.dict("App.server.config.os.environ", {}, clear=True)
    @patch("App.server.config.socket.gethostbyname_ex", side_effect=OSError("dns failed"))
    @patch("App.server.config.socket.gethostname", return_value="host")
    @patch("App.server.config.socket.socket")
    def test_falls_back_to_candidates_when_route_and_hostname_fail(
        self,
        mock_socket_cls,
        _mock_gethostname,
        _mock_gethostbyname_ex,
    ):
        mock_socket = mock_socket_cls.return_value.__enter__.return_value
        mock_socket.connect.side_effect = OSError("no route")

        subnet, source = config._detect_android_hotspot_subnet_with_source()

        self.assertEqual(subnet, "192.168.43")
        self.assertEqual(source, "fallback_candidates")

    @patch.dict("App.server.config.os.environ", {"VRCLASSROOM_ANDROID_SUBNET": "192.168.99"}, clear=True)
    def test_uses_env_override_source(self):
        subnet, source = config._detect_android_hotspot_subnet_with_source()

        self.assertEqual(subnet, "192.168.99")
        self.assertEqual(source, "env_override")


if __name__ == "__main__":
    unittest.main()
