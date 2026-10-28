import importlib.util
from pathlib import Path
import unittest

import banner
import themes


spec = importlib.util.spec_from_file_location('monitor', Path(__file__).with_name('__main__.py'))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class KeyTests(unittest.TestCase):
    def test_cyrillic_letters_open_the_menu(self):
        for key in ('ь', 'Ь'):
            with self.subTest(key=key):
                self.assertEqual(monitor.normalize_key(key), 'm')

    def test_existing_mappings_are_preserved(self):
        self.assertEqual(monitor.normalize_key('й'), 'q')
        self.assertEqual(monitor.normalize_key('Ы'), 's')
        self.assertEqual(monitor.normalize_key('m'), 'm')
        self.assertEqual(monitor.normalize_key('M'), 'm')


class DisplayNameTests(unittest.TestCase):
    def test_custom_name_wins_over_alias(self):
        self.assertEqual(monitor.resolve_display_name('Мой Spark', 'manana'),
                         'Мой Spark')

    def test_alias_is_used_without_a_custom_name(self):
        self.assertEqual(monitor.resolve_display_name('', 'manana'), 'manana')
        self.assertEqual(monitor.resolve_display_name(None, 'manana'), 'manana')
        self.assertEqual(monitor.resolve_display_name('   ', 'manana'), 'manana')

    def test_title_is_the_last_resort(self):
        self.assertEqual(monitor.resolve_display_name('', ''), banner.TITLE)
        self.assertEqual(monitor.resolve_display_name(None, None), banner.TITLE)

    def test_values_are_stripped(self):
        self.assertEqual(monitor.resolve_display_name('  Spark  ', ''), 'Spark')
        self.assertEqual(monitor.resolve_display_name('', '  manana  '), 'manana')


class ThemeCycleTests(unittest.TestCase):
    def test_forward_cycle_follows_the_canonical_order(self):
        seen = [themes.THEME_NAMES[0]]
        for _ in themes.THEME_NAMES[1:]:
            seen.append(monitor.cycle_theme(seen[-1], 1))
        self.assertEqual(seen, list(themes.THEME_NAMES))

    def test_forward_cycle_wraps(self):
        self.assertEqual(monitor.cycle_theme(themes.THEME_NAMES[-1], 1),
                         themes.THEME_NAMES[0])

    def test_backward_cycle_wraps(self):
        self.assertEqual(monitor.cycle_theme(themes.THEME_NAMES[0], -1),
                         themes.THEME_NAMES[-1])

    def test_unknown_current_value_normalizes_first(self):
        self.assertEqual(monitor.cycle_theme('unknown', 1), 'Ice')
        self.assertEqual(monitor.cycle_theme(None, -1), themes.THEME_NAMES[-1])


class FooterTests(unittest.TestCase):
    def test_models_view_uses_static_label_and_highlights_models(self):
        segments = monitor.footer_segments(False, False)
        text = ''.join(part for part, _ in segments)
        self.assertIn('[s] Static', text)
        self.assertIn('[l] LiteLLM', text)
        self.assertEqual([part for part, active in segments if active],
                         ['● [Tab] модели  '])

    def test_usage_view_changes_litellm_to_back(self):
        segments = monitor.footer_segments(False, True)
        text = ''.join(part for part, _ in segments)
        self.assertIn('[l] назад', text)
        self.assertNotIn('[l] LiteLLM', text)
        self.assertEqual([part for part, active in segments if active],
                         ['● [l] назад  '])

    def test_settings_view_highlights_back_and_keeps_static_controls(self):
        segments = monitor.footer_segments(True, False)
        text = ''.join(part for part, _ in segments)
        self.assertIn('[s] назад', text)
        self.assertNotIn('[s] Static', text)
        self.assertEqual([part for part, active in segments if active],
                         ['● [s] назад  '])

    def test_footer_line_joins_the_segments(self):
        self.assertEqual(monitor.footer_line(False, False),
                         ''.join(part for part, _ in monitor.footer_segments(False, False)))


class MenuLinesTests(unittest.TestCase):
    def test_menu_contains_items_and_fixed_width_lines(self):
        lines = monitor.menu_lines('Ice', 'manana', 0)
        self.assertTrue(all(len(line) == monitor.MENU_WIDTH for line in lines))
        text = '\n'.join(lines)
        self.assertIn('Тема: Ice', text)
        self.assertIn('Имя: manana', text)
        self.assertIn('НАСТРОЙКИ', text)
        self.assertIn('m/Esc', text)

    def test_selection_marker_moves(self):
        theme_selected = monitor.menu_lines('Mono', 'manana', 0)
        self.assertTrue(any('▶ Тема:' in line for line in theme_selected))
        self.assertFalse(any('▶ Имя:' in line for line in theme_selected))

        name_selected = monitor.menu_lines('Mono', 'manana', 1)
        self.assertFalse(any('▶ Тема:' in line for line in name_selected))
        self.assertTrue(any('▶ Имя:' in line for line in name_selected))

    def test_editing_prefills_and_marks_the_name_item(self):
        lines = monitor.menu_lines('Emerald', 'manana', 1,
                                   editing=True, input_text='Мой Spark')
        self.assertTrue(all(len(line) == monitor.MENU_WIDTH for line in lines))
        text = '\n'.join(lines)
        self.assertIn('Имя: Мой Spark', text)
        self.assertNotIn('Имя: manana', text)
        self.assertTrue(any('▶ Имя:' in line for line in lines))
        self.assertFalse(any('▶ Тема:' in line for line in lines))
        self.assertIn('Ctrl+U', text)
        self.assertIn('Esc — отмена', text)

    def test_editing_ignores_the_theme_selection_argument(self):
        lines = monitor.menu_lines('VAD-OS', 'manana', 0,
                                   editing=True, input_text='')
        self.assertFalse(any('▶ Тема:' in line for line in lines))
        self.assertTrue(any('▶ Имя:' in line for line in lines))

    def test_error_is_shown_in_the_popup(self):
        lines = monitor.menu_lines('Amber', 'manana', 0, error='нет доступа')
        self.assertTrue(all(len(line) == monitor.MENU_WIDTH for line in lines))
        self.assertTrue(any('Ошибка: нет доступа' in line for line in lines))


if __name__ == '__main__':
    unittest.main()
