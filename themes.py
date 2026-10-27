"""Color themes for the curses dashboard.

Pair roles used by __main__.py: 1 footer, 3 warning/badge, 4 critical,
5-10 banner lines, 7 headings/header, 9 border.  Values are curses
foreground color numbers (basic 0-7 or xterm 256-color 8-255).
"""

THEME_NAMES = ('VAD-OS', 'Ice', 'Emerald', 'Amber', 'Mono')
DEFAULT_THEME = 'VAD-OS'

PALETTES = {
    'VAD-OS': {
        1: 6,    # footer            cyan
        2: 2,    # success           green
        3: 3,    # warning / badge   yellow
        4: 1,    # critical          red
        5: 226,  # banner line 1     bright yellow
        6: 220,  # banner line 2     gold
        7: 214,  # headings / header orange
        8: 208,  # banner line 4     deep orange
        9: 172,  # border            burnt orange
        10: 136, # banner line 6     dark amber
    },
    'Ice': {
        1: 51,   # footer            bright cyan
        2: 120,  # success           pale green
        3: 222,  # warning / badge   pale yellow
        4: 203,  # critical          salmon red
        5: 195,  # banner line 1     ice blue
        6: 159,  # banner line 2     pale sky
        7: 111,  # headings / header sky blue
        8: 105,  # banner line 4     periwinkle
        9: 69,   # border            steel blue
        10: 67,  # banner line 6     slate blue
    },
    'Emerald': {
        1: 42,   # footer            green
        2: 46,   # success           bright green
        3: 220,  # warning / badge   gold
        4: 196,  # critical          red
        5: 154,  # banner line 1     lime
        6: 148,  # banner line 2     yellow-green
        7: 118,  # headings / header bright green
        8: 112,  # banner line 4     green
        9: 71,   # border            sea green
        10: 65,  # banner line 6     forest green
    },
    'Amber': {
        1: 214,  # footer            amber
        2: 142,  # success           olive
        3: 220,  # warning / badge   yellow
        4: 196,  # critical          red
        5: 229,  # banner line 1     pale gold
        6: 223,  # banner line 2     wheat
        7: 217,  # headings / header peach
        8: 209,  # banner line 4     orange
        9: 172,  # border            burnt orange
        10: 130, # banner line 6     brown
    },
    'Mono': {
        1: 252,  # footer            light grey
        2: 250,  # success           grey
        3: 249,  # warning / badge   mid grey
        4: 255,  # critical          white
        5: 255,  # banner line 1     white
        6: 254,  # banner line 2     near white
        7: 253,  # headings / header bright grey
        8: 250,  # banner line 4     grey
        9: 244,  # border            dim grey
        10: 240, # banner line 6     dark grey
    },
}

# Terminals with fewer than 256 colors: keep pairs 1-4 semantically correct
# and collapse the gradient into yellow/cyan.
_BASIC_FALLBACK = {
    1: 6,  # cyan
    2: 2,  # green
    3: 3,  # yellow
    4: 1,  # red
    5: 3,
    6: 3,
    7: 3,
    8: 3,
    9: 6,
    10: 6,
}


def normalize_theme(name):
    """Return the canonical theme name, or DEFAULT_THEME if unknown."""
    if isinstance(name, str):
        folded = name.strip().casefold()
        for theme in THEME_NAMES:
            if theme.casefold() == folded:
                return theme
    return DEFAULT_THEME


def apply_theme(name):
    """Initialize curses color pairs 1..10 for the selected theme."""
    import curses

    colors = PALETTES[normalize_theme(name)]
    try:
        curses.start_color()
        if not curses.has_colors():
            return
        if curses.COLORS < 256:
            colors = _BASIC_FALLBACK
        for pair, fg in colors.items():
            curses.init_pair(pair, fg, curses.COLOR_BLACK)
    except curses.error:
        pass
