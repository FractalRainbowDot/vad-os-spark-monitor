import subprocess
import unittest
from unittest.mock import patch

import ssh_setup


class SetupTests(unittest.TestCase):
    def test_ready_host_never_prompts_or_writes(self):
        with patch.object(ssh_setup, 'probe', return_value=(True, '')), \
             patch.object(ssh_setup, 'confirm') as ask, \
             patch.object(ssh_setup.subprocess, 'run') as run:
            self.assertTrue(ssh_setup.prepare_ssh([{'ip': 'host'}], 'nvidia', 'ssh'))
        ask.assert_not_called()
        run.assert_not_called()

    def test_decline_never_changes_remote(self):
        with patch.object(ssh_setup, 'probe', return_value=(False, 'denied')), \
             patch.object(ssh_setup, 'confirm', return_value=False), \
             patch.object(ssh_setup.subprocess, 'run') as run:
            self.assertTrue(ssh_setup.prepare_ssh([{'ip': 'host'}], 'nvidia', 'ssh'))
        run.assert_not_called()

    def test_password_setup_and_verification(self):
        with patch.object(ssh_setup, 'probe', side_effect=[
                (False, 'host key'), (False, 'denied'), (True, '')]), \
             patch.object(ssh_setup, 'confirm', return_value=True), \
             patch.object(ssh_setup, 'public_key', return_value='ssh-ed25519 AAA test'), \
             patch.object(ssh_setup.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(ssh_setup.prepare_ssh([{'ip': 'host'}], 'nvidia', 'ssh'))
        first, second = [call.args[0] for call in run.call_args_list]
        self.assertIn('StrictHostKeyChecking=ask', first)
        self.assertIn('StrictHostKeyChecking=yes', second)
        self.assertIn('authorized_keys', second[-1])
        self.assertNotIn('input', run.call_args.kwargs)
        self.assertNotIn('capture_output', run.call_args.kwargs)

    def test_changed_key_or_failed_login_never_installs(self):
        with patch.object(ssh_setup, 'probe', return_value=(False, 'changed key')), \
             patch.object(ssh_setup, 'confirm', return_value=True), \
             patch.object(ssh_setup, 'public_key') as key, \
             patch.object(ssh_setup.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 255)):
            ssh_setup.prepare_ssh([{'ip': 'host'}], 'nvidia', 'ssh')
        key.assert_not_called()

    def test_cancel_stops_startup(self):
        with patch.object(ssh_setup, 'probe', return_value=(False, 'denied')), \
             patch.object(ssh_setup, 'confirm', side_effect=KeyboardInterrupt):
            self.assertFalse(ssh_setup.prepare_ssh([{'ip': 'host'}], 'nvidia', 'ssh'))

    def test_command_quotes_public_key_and_deduplicates(self):
        command = ssh_setup.install_command("ssh-ed25519 AAA user's key")
        self.assertIn('grep -qxF', command)
        self.assertIn("'\"'\"'", command)
        self.assertIn('chmod 600', command)


if __name__ == '__main__':
    unittest.main()
