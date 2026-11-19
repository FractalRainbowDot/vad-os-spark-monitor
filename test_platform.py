import importlib.util
import io
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


class FirstRunKeyTests(unittest.TestCase):
    def test_existing_key_never_prompts(self):
        with patch.object(monitor.getpass, 'getpass') as prompt:
            self.assertEqual(monitor.first_run_key('existing'), 'existing')
        prompt.assert_not_called()

    def test_missing_key_uses_hidden_input_and_is_saved(self):
        with patch.object(monitor.getpass, 'getpass', return_value=' test-key '), \
             patch.object(monitor, 'save_api_key') as save:
            self.assertEqual(monitor.first_run_key(''), 'test-key')
        save.assert_called_once_with('test-key')

    def test_enter_skips_without_writing(self):
        with patch.object(monitor.getpass, 'getpass', return_value=''), \
             patch.object(monitor, 'save_api_key') as save:
            self.assertEqual(monitor.first_run_key(''), '')
        save.assert_not_called()


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


class WindowsCursesBootstrapTests(unittest.TestCase):
    def test_non_windows_is_not_touched(self):
        with patch.object(platform_utils, 'is_windows', return_value=False), \
             patch('subprocess.run') as run:
            self.assertFalse(platform_utils.install_windows_curses())
        run.assert_not_called()

    def test_install_uses_the_user_site_outside_a_venv(self):
        with patch.object(platform_utils, 'is_windows', return_value=True), \
             patch.object(platform_utils, 'in_virtualenv', return_value=False), \
             patch.object(platform_utils, 'curses_available', return_value=True), \
             patch('subprocess.run') as run:
            run.return_value = SimpleNamespace(returncode=0)
            self.assertTrue(platform_utils.install_windows_curses())
        command = run.call_args.args[0]
        self.assertEqual(command[0], platform_utils.sys.executable)
        self.assertIn('windows-curses', command)
        self.assertIn('--user', command)

    def test_install_skips_user_flag_inside_a_venv(self):
        with patch.object(platform_utils, 'is_windows', return_value=True), \
             patch.object(platform_utils, 'in_virtualenv', return_value=True), \
             patch.object(platform_utils, 'curses_available', return_value=True), \
             patch('subprocess.run') as run:
            run.return_value = SimpleNamespace(returncode=0)
            self.assertTrue(platform_utils.install_windows_curses())
        self.assertNotIn('--user', run.call_args.args[0])

    def test_failed_pip_returns_false(self):
        with patch.object(platform_utils, 'is_windows', return_value=True), \
             patch.object(platform_utils, 'in_virtualenv', return_value=False), \
             patch('subprocess.run') as run:
            run.return_value = SimpleNamespace(returncode=1)
            self.assertFalse(platform_utils.install_windows_curses())

    def test_unusable_module_after_install_returns_false(self):
        with patch.object(platform_utils, 'is_windows', return_value=True), \
             patch.object(platform_utils, 'in_virtualenv', return_value=False), \
             patch.object(platform_utils, 'curses_available', return_value=False), \
             patch('subprocess.run') as run:
            run.return_value = SimpleNamespace(returncode=0)
            self.assertFalse(platform_utils.install_windows_curses())


class EnsureCursesTests(unittest.TestCase):
    def test_non_windows_does_not_try_to_install(self):
        with patch.object(monitor, 'curses', None), \
             patch.object(monitor, 'is_windows', return_value=False), \
             patch.object(monitor, 'install_windows_curses') as install:
            self.assertIsNone(monitor.ensure_curses())
        install.assert_not_called()

    def test_failed_install_keeps_the_module_missing(self):
        with patch.object(monitor, 'curses', None), \
             patch.object(monitor, 'is_windows', return_value=True), \
             patch.object(monitor, 'install_windows_curses', return_value=False), \
             patch.object(monitor.sys, 'stderr', new=io.StringIO()) as err:
            self.assertIsNone(monitor.ensure_curses())
        self.assertIn('windows-curses', err.getvalue())

    def test_available_module_is_returned_without_pip(self):
        with patch.object(monitor, 'curses', SimpleNamespace(name='curses')), \
             patch.object(monitor, 'install_windows_curses') as install:
            self.assertEqual(monitor.ensure_curses().name, 'curses')
        install.assert_not_called()


if __name__ == '__main__':
    unittest.main()
