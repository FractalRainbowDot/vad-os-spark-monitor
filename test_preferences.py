import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import preferences


class PathTests(unittest.TestCase):
    def test_config_name_is_adjacent_to_source(self):
        self.assertEqual(preferences.CONFIG_NAME, '.spark-monitor.json')
        self.assertEqual(preferences.config_path(),
                         Path(preferences.__file__).resolve().parent / preferences.CONFIG_NAME)

    def test_config_path_uses_archive_directory_for_pyz(self):
        with tempfile.TemporaryDirectory() as directory:
            loader = type('Loader', (), {'archive': str(Path(directory) / 'spark-monitor.pyz')})()
            with patch.object(preferences, '__loader__', loader):
                self.assertEqual(preferences.config_path(),
                                 Path(directory).resolve() / preferences.CONFIG_NAME)


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / preferences.CONFIG_NAME

    def tearDown(self):
        self.directory.cleanup()

    def test_round_trip_writes_owner_only_mode(self):
        values = {'theme': 'dark', 'display_name': 'Ада'}
        preferences.save_preferences(values, self.path)
        self.assertEqual(preferences.load_preferences(self.path), values)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_unknown_keys_are_ignored(self):
        self.path.write_text('{"theme": "dark", "extra": "x", "display_name": 7}',
                             encoding='utf-8')
        self.assertEqual(preferences.load_preferences(self.path), {'theme': 'dark'})
        self.path.unlink()
        preferences.save_preferences(
            {'theme': 'light', 'display_name': 'A', 'extra': 'x'}, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')),
                         {'theme': 'light', 'display_name': 'A'})

    def test_empty_values_are_omitted(self):
        preferences.save_preferences({'theme': '', 'display_name': '   '}, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), {})
        self.assertEqual(preferences.load_preferences(self.path), {})
        self.path.write_text('{"theme": "", "display_name": "", "extra": "x"}',
                             encoding='utf-8')
        self.assertEqual(preferences.load_preferences(self.path), {})

    def test_missing_file_returns_empty_dict(self):
        missing = Path(self.directory.name) / 'absent' / preferences.CONFIG_NAME
        self.assertEqual(preferences.load_preferences(missing), {})

    def test_invalid_json_is_rejected(self):
        self.path.write_text('{not json', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'некорректный JSON'):
            preferences.load_preferences(self.path)

    def test_non_dict_json_is_rejected(self):
        self.path.write_text('[1, 2]', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'объект JSON'):
            preferences.load_preferences(self.path)

    def test_control_characters_are_stripped(self):
        preferences.save_preferences(
            {'theme': 'dar\x00k', 'display_name': '  Nik\nName\x1b  '}, self.path)
        self.assertEqual(preferences.load_preferences(self.path),
                         {'theme': 'dark', 'display_name': 'NikName'})
        self.path.write_text(json.dumps({'theme': 'li\x1bght', 'display_name': 'A\x00B'}),
                             encoding='utf-8')
        self.assertEqual(preferences.load_preferences(self.path),
                         {'theme': 'light', 'display_name': 'AB'})

    def test_display_name_is_capped_at_32_characters(self):
        preferences.save_preferences({'display_name': '  ' + 'Ж' * 40 + '  '}, self.path)
        self.assertEqual(preferences.load_preferences(self.path),
                         {'display_name': 'Ж' * 32})

    def test_oversized_file_is_rejected(self):
        self.path.write_text('{"theme": "' + 'x' * preferences.MAX_SIZE + '"}',
                             encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'слишком большой'):
            preferences.load_preferences(self.path)

    def test_symlink_is_not_followed_on_load(self):
        target = Path(self.directory.name) / 'target.json'
        target.write_text('{"theme": "dark"}', encoding='utf-8')
        self.path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'символической ссылкой'):
            preferences.load_preferences(self.path)

    def test_symlink_destination_is_replaced_not_followed(self):
        target = Path(self.directory.name) / 'target.json'
        target.write_text('{"theme": "original"}', encoding='utf-8')
        self.path.symlink_to(target)
        preferences.save_preferences({'theme': 'dark'}, self.path)
        self.assertEqual(target.read_text(encoding='utf-8'), '{"theme": "original"}')
        self.assertFalse(self.path.is_symlink())
        self.assertEqual(preferences.load_preferences(self.path), {'theme': 'dark'})


if __name__ == '__main__':
    unittest.main()
