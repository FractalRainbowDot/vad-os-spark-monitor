import string
import unittest

import banner


RUSSIAN_ALPHABET = 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'

EXPECTED_HEADER_ART = (
    '   .::::::::. .::::::::. .::::::::.',
    '   : SPARK  : : SPARK  : : SPARK  :',
    "   '::::::::' '::::::::' '::::::::'",
    '        :          :          :',
    "        '..........:..........'",
    '',
)


class HeaderTests(unittest.TestCase):
    def test_header_art_is_unchanged(self):
        self.assertEqual(banner.HEADER_ART, EXPECTED_HEADER_ART)

    def test_layout_length_and_width(self):
        lines = banner.title_banner()
        self.assertEqual(len(lines), 6)
        self.assertTrue(all(len(line) <= 80 for line in lines), lines)

    def test_header_art_prefix_is_preserved(self):
        lines = banner.title_banner()
        for row, line in enumerate(EXPECTED_HEADER_ART):
            self.assertTrue(lines[row].startswith(line[3:]), (row, lines[row]))

    def test_default_title_uses_compact_brand_when_full_does_not_fit(self):
        lines = banner.title_banner()
        self.assertIn(banner.DEFAULT_TITLE, lines[5])
        self.assertIn('█', '\n'.join(lines))
        self.assertEqual(lines[:5], banner.title_banner('VAD-OS')[:5])


class BlockTitleTests(unittest.TestCase):
    def test_returns_five_rows_of_block_characters(self):
        rows = banner.block_title('sample')
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(len(row) == len(rows[0]) for row in rows))
        self.assertIn('█', ''.join(rows))
        self.assertTrue(set(''.join(rows)) <= {'█', '░', ' '})

    def test_all_letters_and_digits_render(self):
        for char in string.ascii_uppercase + string.digits:
            with self.subTest(char=char):
                rows = banner.block_title(char)
                self.assertEqual(len(rows), 5)
                self.assertTrue(all(len(row) == 6 for row in rows))
                self.assertIn('█', ''.join(rows))
        self.assertEqual(len(banner.block_title(string.ascii_uppercase + string.digits)), 5)

    def test_russian_alphabet_renders(self):
        for char in RUSSIAN_ALPHABET:
            with self.subTest(char=char):
                rows = banner.block_title(char)
                self.assertEqual(len(rows), 5)
                self.assertTrue(all(len(row) == 6 for row in rows))
                self.assertIn('█', ''.join(rows))

    def test_lowercase_russian_is_uppercased_for_the_font(self):
        self.assertEqual(banner.block_title('привет'), banner.block_title('ПРИВЕТ'))

    def test_supported_punctuation_renders(self):
        for char in "-_. /":
            with self.subTest(char=char):
                self.assertEqual(len(banner.block_title(char)), 5)

    def test_font_is_well_formed(self):
        expected = set(string.ascii_uppercase + string.digits + ' -_./')
        expected |= set(RUSSIAN_ALPHABET)
        self.assertTrue(expected <= set(banner.BLOCK_FONT))
        for char, glyph in banner.BLOCK_FONT.items():
            with self.subTest(char=char):
                self.assertEqual(len(glyph), 5)
                self.assertTrue(all(len(row) == 5 for row in glyph))
                self.assertTrue(all(set(row) <= {'0', '1'} for row in glyph))

    def test_unsupported_character_raises(self):
        with self.assertRaises((KeyError, ValueError)):
            banner.block_title('Ω')


class TitleBannerTests(unittest.TestCase):
    def test_lowercase_alias_is_drawn_as_a_block_title(self):
        block = banner.block_title('sample')
        lines = banner.title_banner('sample')
        for row in range(5):
            self.assertTrue(lines[row].endswith(block[row]), (row, lines[row]))
        self.assertIn('░', lines[5])

    def test_vad_os_is_drawn_as_a_block_title(self):
        block = banner.block_title('VAD-OS')
        lines = banner.title_banner('VAD-OS')
        self.assertEqual(len(lines), 6)
        for row in range(5):
            self.assertTrue(lines[row].endswith(block[row]), (row, lines[row]))
        self.assertTrue(all(len(line) <= 80 for line in lines))

    def test_russian_name_is_drawn_as_a_block_title(self):
        name = 'ВАД-ОС'
        block = banner.block_title(name)
        lines = banner.title_banner(name)
        self.assertEqual(len(lines), 6)
        for row in range(5):
            self.assertTrue(lines[row].endswith(block[row]), (row, lines[row]))
        self.assertIn('░', lines[5])
        self.assertTrue(all(len(line) <= 80 for line in lines))

    def test_title_is_case_insensitive(self):
        self.assertEqual(banner.title_banner('vad-os')[:5],
                         banner.title_banner('VAD-OS')[:5])
        self.assertEqual(banner.title_banner('вад-ос')[:5],
                         banner.title_banner('ВАД-ОС')[:5])

    def test_unsupported_name_falls_back_to_plain_text(self):
        name = 'Ω'
        lines = banner.title_banner(name)
        self.assertEqual(len(lines), 6)
        self.assertTrue(any(name in line for line in lines), lines)
        self.assertNotIn('█', '\n'.join(lines))
        self.assertTrue(all(len(line) <= 80 for line in lines))

    def test_empty_and_blank_names_use_default(self):
        for name in ('', '   ', None):
            with self.subTest(name=name):
                lines = banner.title_banner(name)
                self.assertTrue(any(banner.DEFAULT_TITLE in line for line in lines), lines)

    def test_long_name_is_truncated_to_width(self):
        lines = banner.title_banner('W' * 100, width=80)
        self.assertEqual(len(lines), 6)
        self.assertTrue(all(len(line) <= 80 for line in lines))
        self.assertEqual(len(lines[5]), 80)
        self.assertIn('W', lines[5])
        self.assertNotIn('█', '\n'.join(lines))

    def test_narrow_width_truncates_the_plain_fallback(self):
        lines = banner.title_banner('VAD-OS', width=40)
        self.assertEqual(len(lines), 6)
        self.assertTrue(all(len(line) <= 40 for line in lines))
        self.assertEqual(lines[5].strip(), 'VAD-O', lines[5])
        self.assertNotIn('█', '\n'.join(lines))

    def test_tiny_widths_never_raise(self):
        for width in (0, 1, 10):
            with self.subTest(width=width):
                lines = banner.title_banner('VAD-OS', width=width)
                self.assertEqual(len(lines), 6)
                self.assertTrue(all(len(line) <= width for line in lines))


if __name__ == '__main__':
    unittest.main()
