from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_publisher.network import proxy_url, browser_proxy


class NetworkTests(unittest.TestCase):
    def test_mac_static_proxy_used_when_environment_unset(self):
        settings = 'HTTPSProxy : 127.0.0.1\nHTTPSEnable : 1\nHTTPSPort : 7897\n'
        with patch.dict(os.environ, {}, clear=True), patch('video_publisher.network.sys.platform', 'darwin'), patch('video_publisher.network.subprocess.check_output', return_value=settings):
            self.assertEqual(proxy_url(), 'http://127.0.0.1:7897')
            self.assertEqual(browser_proxy(), {'server': 'http://127.0.0.1:7897'})

    def test_explicit_environment_proxy_takes_precedence(self):
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://user:secret@proxy.test:8080'}, clear=True), patch('video_publisher.network.subprocess.check_output') as read:
            config = browser_proxy()
            self.assertEqual(config['server'], 'http://proxy.test:8080')
            self.assertEqual(config['username'], 'user')
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
