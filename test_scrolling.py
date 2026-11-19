"""Drive the real dashboard input/render loop without network or a terminal."""

import curses
import importlib.util
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location('scroll_monitor', Path(__file__).with_name('__main__.py'))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class DashboardScrollTests(unittest.TestCase):
    def dashboard(self, keys, mouse_state=0):
        frames, current = [], {}
        screen = MagicMock()
        screen.getmaxyx.return_value = (24, 100)
        screen.erase.side_effect = current.clear
        screen.addnstr.side_effect = lambda y, x, text, *rest: current.update({(y, x): text})
        events = iter(keys + ['q'])

        def read():
            frames.append(dict(current))
            return next(events)

        screen.get_wch.side_effect = read
        args = SimpleNamespace(
            embeddings=False, explain=False, usage=False, settings=False,
            period='2', no_discovery=True, no_update_check=True,
            once=False, interval=1000, user='nvidia')
        usage = MagicMock()
        usage.key_alias.return_value = ''
        with ExitStack() as stack:
            for name, value in (
                    ('load_preferences', {}), ('title_banner', []),
                    ('framed_table', []), ('discovery_rows', []),
                    ('model_tables', [f'row-{i}' for i in range(80)]),
                    ('document_alerts', [[] for _ in range(100)])):
                stack.enter_context(patch.object(monitor, name, return_value=value))
            stack.enter_context(patch.object(curses, 'curs_set'))
            stack.enter_context(patch.object(curses, 'has_colors', return_value=False))
            mousemask = stack.enter_context(patch.object(curses, 'mousemask'))
            stack.enter_context(patch.object(curses, 'mouseinterval'))
            stack.enter_context(patch.object(curses, 'getmouse',
                                             return_value=(0, 5, 10, 0, mouse_state)))
            monitor.run_dashboard(screen, args, [], [], None, usage)
            mousemask.assert_called_once_with(monitor.mouse_wheel_mask())
        return frames

    def first_row(self, frame):
        # Header is at y=1, followed by the scrollable document at y=2.
        return frame[(2, 2)]

    def test_arrows_scroll_the_document(self):
        frames = self.dashboard([curses.KEY_DOWN])
        self.assertEqual(self.first_row(frames[0]), '')
        self.assertEqual(self.first_row(frames[1]), 'row-0')

    def test_wheel_down_scrolls_three_rows(self):
        frames = self.dashboard([curses.KEY_MOUSE], curses.BUTTON5_PRESSED)
        self.assertEqual(self.first_row(frames[1]), 'row-2')

    def test_wheel_up_scrolls_back(self):
        frames = self.dashboard(
            [curses.KEY_DOWN] * 5 + [curses.KEY_MOUSE], curses.BUTTON4_PRESSED)
        self.assertEqual(self.first_row(frames[-1]), 'row-1')

    def test_wheel_up_stays_at_top(self):
        frames = self.dashboard([curses.KEY_MOUSE], curses.BUTTON4_PRESSED)
        self.assertEqual(self.first_row(frames[-1]), '')

    def test_unrelated_mouse_event_does_not_scroll(self):
        frames = self.dashboard([curses.KEY_MOUSE], curses.BUTTON1_PRESSED)
        self.assertEqual(self.first_row(frames[-1]), '')

    def test_wheel_does_not_scroll_behind_menu(self):
        frames = self.dashboard(['m', curses.KEY_MOUSE, 'm'], curses.BUTTON5_PRESSED)
        self.assertEqual(self.first_row(frames[-1]), '')

    def test_wheel_clamps_at_document_end(self):
        frames = self.dashboard([curses.KEY_MOUSE] * 40, curses.BUTTON5_PRESSED)
        self.assertEqual(self.first_row(frames[-1]), 'row-62')


if __name__ == '__main__':
    unittest.main()
