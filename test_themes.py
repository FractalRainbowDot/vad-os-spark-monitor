import unittest
from unittest.mock import call, patch

import curses

import themes


OPENCODE_THEMES = {
    'aura', 'ayu', 'carbonfox', 'catppuccin', 'catppuccin-frappe',
    'catppuccin-macchiato', 'cobalt2', 'cursor', 'dracula', 'everforest',
    'flexoki', 'github', 'gruvbox', 'kanagawa', 'lucent-orng', 'material',
    'matrix', 'mercury', 'monokai', 'nightowl', 'nord', 'one-dark', 'opencode',
    'orng', 'osaka-jade', 'palenight', 'rosepine', 'solarized', 'synthwave84',
    'system', 'tokyonight', 'vercel', 'vesper', 'zenburn',
}


class NormalizeThemeTests(unittest.TestCase):
    def test_exact_name_is_returned(self):
        for name in themes.THEME_NAMES:
            self.assertEqual(themes.normalize_theme(name), name)

    def test_case_insensitive_match(self):
        self.assertEqual(themes.normalize_theme('ice'), 'Ice')
        self.assertEqual(themes.normalize_theme('EMERALD'), 'Emerald')
        self.assertEqual(themes.normalize_theme('amber'), 'Amber')
        self.assertEqual(themes.normalize_theme('vad-os'), 'VAD-OS')

    def test_unknown_and_missing_fall_back_to_default(self):
        self.assertEqual(themes.normalize_theme('does-not-exist'), themes.DEFAULT_THEME)
        self.assertEqual(themes.normalize_theme(''), themes.DEFAULT_THEME)
        self.assertEqual(themes.normalize_theme(None), themes.DEFAULT_THEME)
        self.assertEqual(themes.normalize_theme('VAD'), themes.DEFAULT_THEME)

    def test_all_opencode_builtin_themes_are_available(self):
        self.assertTrue(OPENCODE_THEMES.issubset(themes.THEME_NAMES))

    def test_theme_names_are_unique(self):
        self.assertEqual(len(themes.THEME_NAMES), len(set(themes.THEME_NAMES)))


class PaletteTests(unittest.TestCase):
    def test_every_palette_covers_pairs_one_through_ten(self):
        for name in themes.THEME_NAMES:
            with self.subTest(theme=name):
                self.assertIn(name, themes.PALETTES)
                self.assertEqual(set(themes.PALETTES[name]), set(range(1, 11)))

    def test_every_value_is_a_valid_color_number(self):
        for name in themes.THEME_NAMES:
            for pair, fg in themes.PALETTES[name].items():
                with self.subTest(theme=name, pair=pair):
                    self.assertIsInstance(fg, int)
                    self.assertGreaterEqual(fg, 0)
                    self.assertLessEqual(fg, 255)

    def test_vad_os_palette_matches_existing_dashboard(self):
        self.assertEqual(themes.PALETTES['VAD-OS'], {
            1: curses.COLOR_CYAN,
            2: curses.COLOR_GREEN,
            3: curses.COLOR_YELLOW,
            4: curses.COLOR_RED,
            5: 226,
            6: 220,
            7: 214,
            8: 208,
            9: 172,
            10: 136,
        })


class ApplyThemeTests(unittest.TestCase):
    def test_no_colors_available_does_not_raise_and_skips_pairs(self):
        with patch('curses.start_color') as start_color, \
             patch('curses.has_colors', return_value=False), \
             patch('curses.init_pair') as init_pair:
            themes.apply_theme('Ice')
        start_color.assert_called_once()
        init_pair.assert_not_called()

    def test_256_color_terminal_uses_theme_palette(self):
        with patch('curses.start_color'), \
             patch('curses.has_colors', return_value=True), \
             patch('curses.COLORS', 256, create=True), \
             patch('curses.init_pair') as init_pair:
            themes.apply_theme('Emerald')
        expected = themes.PALETTES['Emerald']
        self.assertEqual(init_pair.call_count, 10)
        for pair, fg in expected.items():
            init_pair.assert_any_call(pair, fg, curses.COLOR_BLACK)

    def test_basic_terminal_uses_safe_fallback(self):
        with patch('curses.start_color'), \
             patch('curses.has_colors', return_value=True), \
             patch('curses.COLORS', 8, create=True), \
             patch('curses.init_pair') as init_pair:
            themes.apply_theme('Amber')
        self.assertEqual(init_pair.call_count, 10)
        for pair in (1, 2, 3, 4):
            self.assertEqual(init_pair.call_args_list[pair - 1], call(
                pair, themes.PALETTES['VAD-OS'][pair], curses.COLOR_BLACK))
        for pair in (5, 6, 7, 8):
            self.assertEqual(init_pair.call_args_list[pair - 1], call(
                pair, curses.COLOR_YELLOW, curses.COLOR_BLACK))
        for pair in (9, 10):
            self.assertEqual(init_pair.call_args_list[pair - 1], call(
                pair, curses.COLOR_CYAN, curses.COLOR_BLACK))

    def test_unknown_theme_falls_back_to_default_palette(self):
        with patch('curses.start_color'), \
             patch('curses.has_colors', return_value=True), \
             patch('curses.COLORS', 256, create=True), \
             patch('curses.init_pair') as init_pair:
            themes.apply_theme('nope')
        expected = themes.PALETTES[themes.DEFAULT_THEME]
        for pair, fg in expected.items():
            init_pair.assert_any_call(pair, fg, curses.COLOR_BLACK)

    def test_curses_error_is_swallowed(self):
        with patch('curses.start_color', side_effect=curses.error('no terminal')), \
             patch('curses.has_colors', return_value=True), \
             patch('curses.init_pair') as init_pair:
            themes.apply_theme('Mono')
        init_pair.assert_not_called()

    def test_init_pair_errors_are_swallowed(self):
        with patch('curses.start_color'), \
             patch('curses.has_colors', return_value=True), \
             patch('curses.COLORS', 256, create=True), \
             patch('curses.init_pair', side_effect=curses.error('bad pair')):
            themes.apply_theme('VAD-OS')

    def test_every_theme_initializes_all_ten_pairs(self):
        with patch('curses.start_color'), \
             patch('curses.has_colors', return_value=True), \
             patch('curses.COLORS', 256, create=True), \
             patch('curses.init_pair') as init_pair:
            for name in themes.THEME_NAMES:
                with self.subTest(theme=name):
                    init_pair.reset_mock()
                    themes.apply_theme(name)
                    self.assertEqual(init_pair.call_count, 10)


if __name__ == '__main__':
    unittest.main()
