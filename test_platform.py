import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import credentials
import platform_utils


spec = importlib.util.spec_from_file_location('monitor', Path(__file__).with_name('__main__.py'))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class PlatformHelperTests(unittest.TestCase):
    def test_windows_ownership_check_does_not_use_getuid(self):
        with patch.object(platform_utils.os, 'name', 'nt'):
            self.assertTrue(platform_utils.owned_by_current_user(
                SimpleNamespace(st_mode=0o100644, st_uid=123)))

    def test_windows_secure_file_uses_icacls(self):
        with patch.object(platform_utils.os, 'name', 'nt'), \
             patch.dict(platform_utils.os.environ, {'USERNAME': 'TestUser'}), \
             patch('subprocess.run') as run:
            platform_utils.secure_file('C:\\data\\.env')
        run.assert_called_once()
        args = run.call_args.args[0]
        self.assertEqual(args[0], 'icacls')
        self.assertEqual(args[1], 'C:\\data\\.env')
        self.assertIn('TestUser:F', args)


class WindowsKeyTests(unittest.TestCase):
    def test_windows_load_does_not_apply_unix_mode_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('LITELLM_API_KEY=secret-value\n', encoding='utf-8')
            os.chmod(path, 0o644)
            with patch.object(credentials, 'is_windows', return_value=True), \
                 patch.object(credentials, 'owned_by_current_user', return_value=True):
                self.assertEqual(credentials.load_api_key(path), 'secret-value')

    def test_windows_save_uses_the_acl_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            with patch.object(credentials, 'is_windows', return_value=True), \
                 patch.object(credentials, 'owned_by_current_user', return_value=True), \
                 patch.object(credentials, 'secure_file') as secure:
                credentials.save_api_key('secret-value', path)
            secure.assert_called_once_with(path)
            self.assertIn('LITELLM_API_KEY=secret-value',
                          path.read_text(encoding='utf-8'))

    def test_windows_ssh_falls_back_to_openssh_feature_path(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh = Path(directory) / 'System32' / 'OpenSSH' / 'ssh.exe'
            ssh.parent.mkdir(parents=True)
            ssh.write_bytes(b'')
            with patch.object(monitor.os, 'name', 'nt'), \
                 patch.object(monitor.shutil, 'which', return_value=None), \
                 patch.dict(monitor.os.environ, {'WINDIR': directory}):
                self.assertEqual(monitor.ssh_binary(), str(ssh))


if __name__ == '__main__':
    unittest.main()
