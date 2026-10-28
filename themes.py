"""Color themes for the curses dashboard.

Includes the five original VAD-OS themes and 34 adapted OpenCode built-in
themes (including the `system` ANSI fallback).  Pair roles used by
__main__.py: 1 footer, 3 warning/badge, 4 critical, 5-10 banner lines,
7 headings/header and active-footer accent, 9 border.  Values are curses
foreground color numbers (basic 0-7 or xterm 256-color 8-255).
"""

THEME_NAMES = (
    'VAD-OS', 'Ice', 'Emerald', 'Amber',
    'Mono', 'aura', 'ayu', 'carbonfox',
    'catppuccin', 'catppuccin-frappe', 'catppuccin-macchiato', 'cobalt2',
    'cursor', 'dracula', 'everforest', 'flexoki',
    'github', 'gruvbox', 'kanagawa', 'lucent-orng',
    'material', 'matrix', 'mercury', 'monokai',
    'nightowl', 'nord', 'one-dark', 'opencode',
    'orng', 'osaka-jade', 'palenight', 'rosepine',
    'solarized', 'synthwave84', 'system', 'tokyonight',
    'vercel', 'vesper', 'zenburn',
)
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
    # OpenCode built-in themes: dark variants; `system` is a safe
    # ANSI-style fallback.  Each palette uses pairs 1..10.
    #
    'aura': {
        1: 218,  # footer
        2: 114,  # success
        3: 222,  # warning / badge
        4: 203,  # critical
        5: 213,  # banner line 1
        6: 177,  # banner line 2
        7: 225,  # accent / header / active
        8: 162,  # banner line 4
        9:  96,  # border
        10:  53,  # banner line 6
    },
    'ayu': {
        1:  73,  # footer
        2: 114,  # success
        3: 179,  # warning / badge
        4: 203,  # critical
        5: 214,  # banner line 1
        6: 208,  # banner line 2
        7: 229,  # accent / header / active
        8: 173,  # banner line 4
        9:  66,  # border
        10:  59,  # banner line 6
    },
    'carbonfox': {
        1: 110,  # footer
        2:  71,  # success
        3: 214,  # warning / badge
        4: 167,  # critical
        5: 208,  # banner line 1
        6: 202,  # banner line 2
        7: 252,  # accent / header / active
        8: 166,  # banner line 4
        9:  60,  # border
        10:  58,  # banner line 6
    },
    'catppuccin': {
        1: 152,  # footer
        2: 151,  # success
        3: 223,  # warning / badge
        4: 217,  # critical
        5: 213,  # banner line 1
        6: 146,  # banner line 2
        7: 183,  # accent / header / active
        8: 104,  # banner line 4
        9: 103,  # border
        10:  60,  # banner line 6
    },
    'catppuccin-frappe': {
        1: 110,  # footer
        2: 150,  # success
        3: 222,  # warning / badge
        4: 174,  # critical
        5: 182,  # banner line 1
        6: 140,  # banner line 2
        7: 147,  # accent / header / active
        8: 104,  # banner line 4
        9: 103,  # border
        10:  61,  # banner line 6
    },
    'catppuccin-macchiato': {
        1: 116,  # footer
        2: 114,  # success
        3: 220,  # warning / badge
        4: 210,  # critical
        5: 183,  # banner line 1
        6: 111,  # banner line 2
        7: 189,  # accent / header / active
        8:  62,  # banner line 4
        9:  60,  # border
        10:  24,  # banner line 6
    },
    'cobalt2': {
        1:  45,  # footer
        2:  77,  # success
        3: 220,  # warning / badge
        4: 196,  # critical
        5:  39,  # banner line 1
        6:  33,  # banner line 2
        7: 226,  # accent / header / active
        8:  27,  # banner line 4
        9:  31,  # border
        10:  18,  # banner line 6
    },
    'cursor': {
        1: 117,  # footer
        2: 114,  # success
        3: 221,  # warning / badge
        4: 204,  # critical
        5: 111,  # banner line 1
        6: 105,  # banner line 2
        7: 255,  # accent / header / active
        8:  63,  # banner line 4
        9:  61,  # border
        10:  54,  # banner line 6
    },
    'dracula': {
        1: 141,  # footer
        2:  84,  # success
        3: 215,  # warning / badge
        4: 210,  # critical
        5: 212,  # banner line 1
        6: 207,  # banner line 2
        7: 231,  # accent / header / active
        8: 135,  # banner line 4
        9:  99,  # border
        10:  55,  # banner line 6
    },
    'everforest': {
        1: 109,  # footer
        2: 108,  # success
        3: 179,  # warning / badge
        4: 131,  # critical
        5: 150,  # banner line 1
        6: 143,  # banner line 2
        7: 192,  # accent / header / active
        8: 107,  # banner line 4
        9:  65,  # border
        10:  22,  # banner line 6
    },
    'flexoki': {
        1: 109,  # footer
        2: 107,  # success
        3: 173,  # warning / badge
        4: 167,  # critical
        5: 179,  # banner line 1
        6: 137,  # banner line 2
        7: 223,  # accent / header / active
        8: 130,  # banner line 4
        9:  66,  # border
        10:  58,  # banner line 6
    },
    'github': {
        1: 249,  # footer
        2:  77,  # success
        3: 179,  # warning / badge
        4: 203,  # critical
        5:  75,  # banner line 1
        6:  74,  # banner line 2
        7: 111,  # accent / header / active
        8:  67,  # banner line 4
        9: 238,  # border
        10:  25,  # banner line 6
    },
    'gruvbox': {
        1: 108,  # footer
        2: 149,  # success
        3: 214,  # warning / badge
        4: 203,  # critical
        5: 220,  # banner line 1
        6: 208,  # banner line 2
        7: 220,  # accent / header / active
        8: 166,  # banner line 4
        9:  94,  # border
        10: 130,  # banner line 6
    },
    'kanagawa': {
        1: 109,  # footer
        2: 107,  # success
        3: 180,  # warning / badge
        4: 167,  # critical
        5: 117,  # banner line 1
        6:  73,  # banner line 2
        7: 110,  # accent / header / active
        8:  66,  # banner line 4
        9:  60,  # border
        10:  23,  # banner line 6
    },
    'lucent-orng': {
        1: 216,  # footer
        2: 150,  # success
        3: 222,  # warning / badge
        4: 210,  # critical
        5: 223,  # banner line 1
        6: 216,  # banner line 2
        7: 209,  # accent / header / active
        8: 173,  # banner line 4
        9: 137,  # border
        10:  95,  # banner line 6
    },
    'material': {
        1: 117,  # footer
        2: 150,  # success
        3: 222,  # warning / badge
        4: 210,  # critical
        5: 111,  # banner line 1
        6: 176,  # banner line 2
        7: 183,  # accent / header / active
        8:  62,  # banner line 4
        9:  60,  # border
        10:  61,  # banner line 6
    },
    'matrix': {
        1: 120,  # footer
        2:  41,  # success
        3: 148,  # warning / badge
        4: 196,  # critical
        5: 118,  # banner line 1
        6:  47,  # banner line 2
        7:  46,  # accent / header / active
        8:  34,  # banner line 4
        9:  28,  # border
        10:  22,  # banner line 6
    },
    'mercury': {
        1: 110,  # footer
        2:  41,  # success
        3: 222,  # warning / badge
        4: 203,  # critical
        5: 255,  # banner line 1
        6: 153,  # banner line 2
        7: 117,  # accent / header / active
        8: 110,  # banner line 4
        9:  68,  # border
        10:  60,  # banner line 6
    },
    'monokai': {
        1: 117,  # footer
        2: 148,  # success
        3: 186,  # warning / badge
        4: 197,  # critical
        5: 197,  # banner line 1
        6: 148,  # banner line 2
        7: 198,  # accent / header / active
        8: 141,  # banner line 4
        9:  96,  # border
        10:  88,  # banner line 6
    },
    'nightowl': {
        1: 116,  # footer
        2: 149,  # success
        3: 222,  # warning / badge
        4: 204,  # critical
        5: 117,  # banner line 1
        6: 116,  # banner line 2
        7: 111,  # accent / header / active
        8:  69,  # banner line 4
        9:  60,  # border
        10:  24,  # banner line 6
    },
    'nord': {
        1: 110,  # footer
        2: 151,  # success
        3: 180,  # warning / badge
        4: 167,  # critical
        5: 195,  # banner line 1
        6: 110,  # banner line 2
        7: 152,  # accent / header / active
        8:  66,  # banner line 4
        9:  60,  # border
        10:  24,  # banner line 6
    },
    'one-dark': {
        1:  73,  # footer
        2: 150,  # success
        3: 180,  # warning / badge
        4: 168,  # critical
        5: 111,  # banner line 1
        6: 176,  # banner line 2
        7:  75,  # accent / header / active
        8: 139,  # banner line 4
        9:  60,  # border
        10:  54,  # banner line 6
    },
    'opencode': {
        1: 108,  # footer
        2: 114,  # success
        3: 214,  # warning / badge
        4: 203,  # critical
        5: 255,  # banner line 1
        6: 250,  # banner line 2
        7:  41,  # accent / header / active
        8: 245,  # banner line 4
        9: 240,  # border
        10: 236,  # banner line 6
    },
    'orng': {
        1: 214,  # footer
        2: 142,  # success
        3: 220,  # warning / badge
        4: 203,  # critical
        5: 229,  # banner line 1
        6: 214,  # banner line 2
        7: 208,  # accent / header / active
        8: 172,  # banner line 4
        9: 130,  # border
        10:  94,  # banner line 6
    },
    'osaka-jade': {
        1: 115,  # footer
        2:  77,  # success
        3: 179,  # warning / badge
        4: 174,  # critical
        5: 121,  # banner line 1
        6: 114,  # banner line 2
        7: 122,  # accent / header / active
        8:  78,  # banner line 4
        9:  65,  # border
        10:  29,  # banner line 6
    },
    'palenight': {
        1: 146,  # footer
        2: 150,  # success
        3: 179,  # warning / badge
        4: 168,  # critical
        5: 111,  # banner line 1
        6: 105,  # banner line 2
        7: 183,  # accent / header / active
        8: 104,  # banner line 4
        9:  61,  # border
        10:  54,  # banner line 6
    },
    'rosepine': {
        1: 152,  # footer
        2: 149,  # success
        3: 179,  # warning / badge
        4: 174,  # critical
        5: 182,  # banner line 1
        6: 176,  # banner line 2
        7: 217,  # accent / header / active
        8: 139,  # banner line 4
        9:  96,  # border
        10:  90,  # banner line 6
    },
    'solarized': {
        1: 109,  # footer
        2:  64,  # success
        3: 136,  # warning / badge
        4: 160,  # critical
        5:  74,  # banner line 1
        6:  32,  # banner line 2
        7:  39,  # accent / header / active
        8:  66,  # banner line 4
        9:  60,  # border
        10:  24,  # banner line 6
    },
    'synthwave84': {
        1:  51,  # footer
        2:  84,  # success
        3: 214,  # warning / badge
        4: 197,  # critical
        5: 207,  # banner line 1
        6: 201,  # banner line 2
        7: 213,  # accent / header / active
        8: 165,  # banner line 4
        9:  99,  # border
        10:  57,  # banner line 6
    },
    'system': {
        1:  45,  # footer
        2:  40,  # success
        3: 220,  # warning / badge
        4: 196,  # critical
        5: 255,  # banner line 1
        6: 250,  # banner line 2
        7: 117,  # accent / header / active
        8: 111,  # banner line 4
        9:  33,  # border
        10:  67,  # banner line 6
    },
    'tokyonight': {
        1: 117,  # footer
        2: 119,  # success
        3: 179,  # warning / badge
        4: 203,  # critical
        5: 111,  # banner line 1
        6: 105,  # banner line 2
        7: 147,  # accent / header / active
        8: 104,  # banner line 4
        9:  68,  # border
        10:  61,  # banner line 6
    },
    'vercel': {
        1: 250,  # footer
        2:  78,  # success
        3: 179,  # warning / badge
        4: 167,  # critical
        5: 255,  # banner line 1
        6: 252,  # banner line 2
        7: 117,  # accent / header / active
        8: 245,  # banner line 4
        9: 240,  # border
        10: 238,  # banner line 6
    },
    'vesper': {
        1: 137,  # footer
        2: 107,  # success
        3: 214,  # warning / badge
        4: 174,  # critical
        5: 222,  # banner line 1
        6: 179,  # banner line 2
        7: 216,  # accent / header / active
        8: 173,  # banner line 4
        9:  95,  # border
        10:  94,  # banner line 6
    },
    'zenburn': {
        1: 180,  # footer
        2: 107,  # success
        3: 179,  # warning / badge
        4: 167,  # critical
        5: 223,  # banner line 1
        6: 187,  # banner line 2
        7: 151,  # accent / header / active
        8: 109,  # banner line 4
        9: 102,  # border
        10: 144,  # banner line 6
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
