"""Native regression: feed wheel records through Windows/PDCurses, not mocks."""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def console_probe():
    import curses
    spec = importlib.util.spec_from_file_location('wheel_monitor', Path(__file__).with_name('__main__.py'))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    kernel = ctypes.windll.kernel32
    kernel.GetStdHandle.restype = ctypes.c_void_p
    handle = ctypes.c_void_p(kernel.GetStdHandle(-10))

    class Coord(ctypes.Structure):
        _fields_ = [('x', ctypes.c_short), ('y', ctypes.c_short)]

    class Mouse(ctypes.Structure):
        _fields_ = [('position', Coord), ('buttons', ctypes.c_uint32),
                    ('modifiers', ctypes.c_uint32), ('flags', ctypes.c_uint32)]

    class Event(ctypes.Union):
        _fields_ = [('mouse', Mouse), ('padding', ctypes.c_byte * 16)]

    class Record(ctypes.Structure):
        _fields_ = [('kind', ctypes.c_uint16), ('event', Event)]

    assert ctypes.sizeof(Record) == 20
    results = []

    def run(screen):
        screen.keypad(True)
        screen.timeout(1000)
        mask = monitor.mouse_wheel_mask()
        curses.mousemask(mask)
        curses.mouseinterval(0)
        for delta in (120, -120):
            curses.flushinp()
            record = Record()
            record.kind = 2  # MOUSE_EVENT
            record.event.mouse.position = Coord(5, 5)
            record.event.mouse.buttons = (delta & 0xffff) << 16
            record.event.mouse.flags = 4  # MOUSE_WHEELED
            count = ctypes.c_uint32()
            if not kernel.WriteConsoleInputW(handle, ctypes.byref(record), 1, ctypes.byref(count)):
                raise ctypes.WinError()
            key = screen.get_wch()
            state = curses.getmouse()[4] if key == curses.KEY_MOUSE else None
            results.append({'delta': delta, 'state': state, 'mask': mask})

    curses.wrapper(run)
    Path(sys.argv[2]).write_text(json.dumps(results), encoding='utf-8')


@unittest.skipUnless(os.name == 'nt', 'Windows console regression')
class NativeWheelTests(unittest.TestCase):
    def test_real_wheel_records_retain_direction(self):
        preferred = Path.home() / 'AppData/Local/Temp/opencode'
        with tempfile.TemporaryDirectory(dir=preferred if preferred.is_dir() else None) as folder:
            report = Path(folder) / 'mouse.json'
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), '--console-probe', str(report)],
                creationflags=subprocess.CREATE_NEW_CONSOLE, timeout=20, check=False)
            self.assertEqual(process.returncode, 0, 'Native console probe failed')
            events = json.loads(report.read_text(encoding='utf-8'))
            import curses
            self.assertEqual(len(events), 2)
            self.assertTrue(events[0]['state'] & curses.BUTTON4_PRESSED, events)
            self.assertTrue(events[1]['state'] & curses.BUTTON5_PRESSED, events)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--console-probe':
        console_probe()
    else:
        unittest.main()
