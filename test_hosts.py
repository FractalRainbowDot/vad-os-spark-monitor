import json
import subprocess
import unittest
from unittest.mock import patch

import hosts


def peer(name, online=True, os_name='linux', ips=('100.64.0.1', 'fd7a::1')):
    return {'HostName': name, 'OS': os_name, 'Online': online, 'TailscaleIPs': list(ips)}


class HostDiscoveryTests(unittest.TestCase):
    def payload(self, peers):
        return json.dumps({'Peer': {str(index): peer for index, peer in enumerate(peers)}})

    def test_online_linux_sparks_only_and_ipv4(self):
        data = self.payload([
            peer('spark-bbb', ips=('100.64.0.9',)),
            peer('spark-aaa', ips=('fd7a::5', '100.64.0.3')),
            peer('spark-off', online=False),
            peer('spark-win', os_name='windows'),
            peer('workstation', ips=('100.64.0.4',)),
        ])
        with patch('shutil.which', return_value='/usr/bin/tailscale'), \
             patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, data, '')):
            found, error = hosts.discover_hosts()
        self.assertIsNone(error)
        self.assertEqual(found, [{'name': 'spark-aaa', 'ip': '100.64.0.3'},
                                 {'name': 'spark-bbb', 'ip': '100.64.0.9'}])

    def test_health_warning_exit_code_with_valid_json(self):
        data = self.payload([peer('spark-a', ips=('100.64.0.2',))])
        with patch('shutil.which', return_value='/usr/bin/tailscale'), \
             patch('subprocess.run', return_value=subprocess.CompletedProcess([], 2, data, '')):
            found, error = hosts.discover_hosts()
        self.assertIsNone(error)
        self.assertEqual(len(found), 1)

    def test_pattern_override(self):
        data = self.payload([peer('gpu-node-1', ips=('100.64.0.8',)), peer('spark-a')])
        with patch('shutil.which', return_value='/usr/bin/tailscale'), \
             patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, data, '')):
            found, _ = hosts.discover_hosts(r'gpu-node')
        self.assertEqual([host['name'] for host in found], ['gpu-node-1'])

    def test_default_pattern_accepts_spark01_and_rejects_myspark(self):
        data = self.payload([peer('spark01', ips=('100.64.0.6',)),
                             peer('myspark', ips=('100.64.0.7',))])
        with patch('shutil.which', return_value='/usr/bin/tailscale'), \
             patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, data, '')):
            found, _ = hosts.discover_hosts()
        self.assertEqual([host['name'] for host in found], ['spark01'])

    def test_missing_cli_is_actionable(self):
        with patch('shutil.which', return_value=None):
            found, error = hosts.discover_hosts()
        self.assertEqual(found, [])
        self.assertIn('Tailscale', error)

    def test_no_sparks_is_reported(self):
        data = self.payload([peer('workstation')])
        with patch('shutil.which', return_value='/usr/bin/tailscale'), \
             patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, data, '')):
            found, error = hosts.discover_hosts()
        self.assertEqual(found, [])
        self.assertIn('не найдены', error)

    def test_invalid_json_is_reported(self):
        with patch('shutil.which', return_value='/usr/bin/tailscale'), \
             patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'not json', '')):
            found, error = hosts.discover_hosts()
        self.assertEqual(found, [])
        self.assertIn('Tailscale', error)


if __name__ == '__main__':
    unittest.main()
