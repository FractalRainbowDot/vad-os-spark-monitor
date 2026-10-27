import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import updater


def make_zip(path, names=('__main__.py', 'credentials.py')):
    with zipfile.ZipFile(path, 'w') as archive:
        for name in names:
            archive.writestr(name, 'print(1)\n')
    return Path(path) if isinstance(path, (str, os.PathLike)) else None


class VersionTests(unittest.TestCase):
    def test_comparison(self):
        self.assertTrue(updater.is_newer('v1.2.0', '1.1.9'))
        self.assertTrue(updater.is_newer('1.10', '1.9.9'))
        self.assertFalse(updater.is_newer('1.0.0', '1.0'))
        self.assertFalse(updater.is_newer('not-a-version', '1.0.0'))

    def test_notice_only_for_relevant_states(self):
        self.assertIn('перезапустите', updater.notice({'status': 'updated', 'version': '2.0.0'}))
        self.assertIn('2.0.0', updater.notice({'status': 'available', 'version': '2.0.0'}))
        self.assertIsNone(updater.notice({'status': 'current'}))
        self.assertIsNone(updater.notice({'status': 'error'}))

    def test_version_badge_for_new_release_only(self):
        self.assertEqual(updater.version_badge({'status': 'updated', 'version': '2.0.0'}),
                         '↑ v2.0.0')
        self.assertEqual(updater.version_badge({'status': 'available', 'version': 'v2.0.0'}),
                         '↑ v2.0.0')
        self.assertEqual(updater.version_badge({'status': 'current'}), '')
        self.assertEqual(updater.version_badge({'status': 'error'}), '')
        self.assertEqual(updater.version_badge(None), '')


class RecheckTests(unittest.TestCase):
    def test_terminal_states_stop_rechecking(self):
        for status in ('updated', 'available', 'unavailable'):
            self.assertFalse(updater.should_recheck({'status': status}), status)

    def test_retryable_states_keep_rechecking(self):
        self.assertTrue(updater.should_recheck({'status': 'current'}))
        self.assertTrue(updater.should_recheck({'status': 'error', 'error': 'нет связи с GitHub'}))

    def test_missing_or_unknown_state_keeps_rechecking(self):
        self.assertTrue(updater.should_recheck({}))
        self.assertTrue(updater.should_recheck(None))
        self.assertTrue(updater.should_recheck({'status': 'unexpected'}))


class DownloadTests(unittest.TestCase):
    def test_verified_download(self):
        data = io.BytesIO()
        make_zip(data)
        payload = data.getvalue()
        checksum = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory, \
             patch('updater._open', return_value=io.BytesIO(payload)):
            candidate = updater._download({'browser_download_url': 'https://example.invalid/a'},
                                          checksum, directory, 5)
            self.assertTrue(Path(candidate).is_file())
            self.assertEqual(Path(candidate).read_bytes(), payload)
            self.assertEqual(Path(candidate).stat().st_mode & 0o777, 0o755)
            Path(candidate).unlink()

    def test_checksum_mismatch_deletes_candidate(self):
        data = io.BytesIO()
        make_zip(data)
        with tempfile.TemporaryDirectory() as directory, \
             patch('updater._open', return_value=io.BytesIO(data.getvalue())):
            with self.assertRaises(ValueError):
                updater._download({'browser_download_url': 'https://example.invalid/a'},
                                  '0' * 64, directory, 5)
            self.assertEqual(os.listdir(directory), [])

    def test_non_zip_is_rejected(self):
        payload = b'not a zip'
        checksum = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory, \
             patch('updater._open', return_value=io.BytesIO(payload)):
            with self.assertRaises(ValueError):
                updater._download({'browser_download_url': 'https://example.invalid/a'},
                                  checksum, directory, 5)


class InstallTests(unittest.TestCase):
    def test_atomic_replace_keeps_backup_and_env(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = make_zip(Path(directory) / 'spark-monitor.pyz')
            env = Path(directory) / '.env'
            env.write_text('LITELLM_API_KEY=secret\n')
            candidate = make_zip(Path(directory) / 'candidate.pyz', names=('__main__.py',))
            updater.install(archive, candidate)
            self.assertEqual(zipfile.ZipFile(archive).namelist(), ['__main__.py'])
            self.assertTrue((Path(directory) / 'spark-monitor.pyz.prev').is_file())
            self.assertEqual(env.read_text(), 'LITELLM_API_KEY=secret\n')
            self.assertFalse(candidate.exists())

    def test_refuses_non_pyz(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'program.py'
            target.write_text('')
            with self.assertRaises(ValueError):
                updater.install(target, target)


class PerformUpdateTests(unittest.TestCase):
    def release(self, tag, digest=None, checksum_asset=None):
        asset = {'name': 'spark-monitor.pyz', 'browser_download_url': 'https://example.invalid/a'}
        if digest:
            asset['digest'] = 'sha256:' + digest
        assets = [asset]
        if checksum_asset:
            assets.append({'name': 'spark-monitor.pyz.sha256',
                           'browser_download_url': 'https://example.invalid/sha'})
        return {'tag_name': tag, 'assets': assets}, asset, checksum_asset

    def test_current_version_is_not_downloaded(self):
        payload = {'tag_name': 'v1.0.0', 'assets': []}
        with patch('updater._release', return_value=(payload, {}, None)):
            self.assertEqual(updater.perform_update('x.pyz')['status'], 'current')

    def test_missing_checksum_only_notifies(self):
        payload, asset, _ = self.release('v2.0.0')
        with patch('updater._release', return_value=(payload, asset, None)):
            state = updater.perform_update('x.pyz')
        self.assertEqual(state['status'], 'available')
        self.assertEqual(state['version'], '2.0.0')

    def test_updated_installs_verified_file(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = make_zip(Path(directory) / 'spark-monitor.pyz')
            payload, asset, _ = self.release('v2.0.0', digest='a' * 64)
            candidate = make_zip(Path(directory) / 'candidate.pyz', names=('__main__.py',))
            with patch('updater._release', return_value=(payload, asset, 'a' * 64)), \
                 patch('updater._download', return_value=str(candidate)):
                state = updater.perform_update(archive)
            self.assertEqual(state, {'status': 'updated', 'version': '2.0.0'})

    def test_release_requires_checksum(self):
        payload = {'tag_name': 'v2.0.0', 'assets': [
            {'name': 'spark-monitor.pyz', 'browser_download_url': 'https://example.invalid/a'}]}
        with patch('updater._open', return_value=io.BytesIO(json.dumps(payload).encode())):
            _, _, checksum = updater._release('owner/repo', 5)
        self.assertIsNone(checksum)


if __name__ == '__main__':
    unittest.main()
