"""Header banner rendering for the monitor.

The banner is deliberately self-contained: it has no terminal, network or
application dependencies, so a display name can be rendered anywhere the
module is importable.
"""

TITLE = 'VAD-OS Spark Monitor'
DEFAULT_TITLE = TITLE

HEADER_ART = (
    '   .::::::::. .::::::::. .::::::::.',
    '   : SPARK  : : SPARK  : : SPARK  :',
    "   '::::::::' '::::::::' '::::::::'",
    '        :          :          :',
    "        '..........:..........'",
    '',
)


# A 5x5 block font. Each row is five columns of '1' (ink) and '0' (blank).
BLOCK_FONT = {
    ' ': ('00000', '00000', '00000', '00000', '00000'),
    'A': ('01110', '11011', '11111', '11011', '11011'),
    'B': ('11110', '11011', '11110', '11011', '11110'),
    'C': ('01111', '11000', '11000', '11000', '01111'),
    'D': ('11110', '11011', '11011', '11011', '11110'),
    'E': ('11111', '11000', '11110', '11000', '11111'),
    'F': ('11111', '11000', '11110', '11000', '11000'),
    'G': ('01111', '11000', '11011', '11011', '01111'),
    'H': ('11011', '11011', '11111', '11011', '11011'),
    'I': ('11111', '00100', '00100', '00100', '11111'),
    'J': ('00111', '00010', '00010', '11010', '01100'),
    'K': ('11011', '11010', '11100', '11010', '11011'),
    'L': ('11000', '11000', '11000', '11000', '11111'),
    'M': ('11011', '11111', '11111', '11011', '11011'),
    'N': ('11001', '11101', '11111', '11011', '11001'),
    'O': ('01110', '11011', '11011', '11011', '01110'),
    'P': ('11110', '11011', '11110', '11000', '11000'),
    'Q': ('01110', '11011', '11011', '11101', '01111'),
    'R': ('11110', '11011', '11110', '11011', '11011'),
    'S': ('01111', '11000', '01110', '00011', '11110'),
    'T': ('11111', '00100', '00100', '00100', '00100'),
    'U': ('11011', '11011', '11011', '11011', '01110'),
    'V': ('10001', '10001', '10001', '01010', '00100'),
    'W': ('11011', '11011', '11111', '10101', '01010'),
    'X': ('10001', '01010', '00100', '01010', '10001'),
    'Y': ('10001', '01010', '00100', '00100', '00100'),
    'Z': ('11111', '00010', '00100', '01000', '11111'),
    # Russian alphabet. Visually identical Latin letters reuse their glyphs.
    'А': ('01110', '11011', '11111', '11011', '11011'),
    'Б': ('11111', '11000', '11110', '11011', '11110'),
    'В': ('11110', '11011', '11110', '11011', '11110'),
    'Г': ('11111', '11000', '11000', '11000', '11000'),
    'Д': ('01110', '01010', '01010', '11111', '10001'),
    'Е': ('11111', '11000', '11110', '11000', '11111'),
    'Ж': ('10001', '01010', '11111', '01010', '10001'),
    'З': ('11110', '00001', '01110', '00001', '11110'),
    'И': ('10001', '10011', '10101', '11001', '10001'),
    'Й': ('00100', '10001', '10011', '10101', '11001'),
    'К': ('11011', '11010', '11100', '11010', '11011'),
    'Л': ('01110', '01010', '01010', '01010', '11001'),
    'М': ('10001', '11011', '10101', '10001', '10001'),
    'Н': ('11011', '11011', '11111', '11011', '11011'),
    'О': ('01110', '11011', '11011', '11011', '01110'),
    'П': ('11111', '11011', '11011', '11011', '11011'),
    'Р': ('11110', '11011', '11110', '11000', '11000'),
    'С': ('01111', '11000', '11000', '11000', '01111'),
    'Т': ('11111', '00100', '00100', '00100', '00100'),
    'У': ('10001', '10001', '01110', '00010', '11100'),
    'Ф': ('00100', '11111', '10101', '11111', '00100'),
    'Х': ('10001', '01010', '00100', '01010', '10001'),
    'Ц': ('11011', '11011', '11011', '11111', '00001'),
    'Ч': ('10001', '10001', '11111', '00001', '00001'),
    'Ш': ('10101', '10101', '10101', '10101', '11111'),
    'Щ': ('10101', '10101', '10101', '11111', '00001'),
    'Ъ': ('11100', '00100', '00110', '00101', '00110'),
    'Ы': ('11001', '11001', '11011', '11011', '11111'),
    'Ь': ('11000', '11000', '11110', '11011', '11110'),
    'Э': ('11110', '00001', '01111', '00001', '11110'),
    'Ю': ('10001', '10001', '10111', '10011', '01110'),
    'Я': ('01111', '11011', '01111', '11011', '11011'),
    '0': ('01110', '11011', '11011', '11011', '01110'),
    '1': ('00100', '01100', '00100', '00100', '01110'),
    '2': ('11110', '00001', '01110', '10000', '11111'),
    '3': ('11110', '00001', '01110', '00001', '11110'),
    '4': ('00010', '00110', '01010', '11111', '00010'),
    '5': ('11111', '10000', '11110', '00001', '11110'),
    '6': ('01110', '10000', '11110', '10001', '01110'),
    '7': ('11111', '00001', '00010', '00100', '01000'),
    '8': ('01110', '10001', '01110', '10001', '01110'),
    '9': ('01110', '10001', '01111', '00001', '01110'),
    '-': ('00000', '00000', '11111', '00000', '00000'),
    '_': ('00000', '00000', '00000', '00000', '11111'),
    '.': ('00000', '00000', '00000', '00000', '00100'),
    '/': ('00001', '00010', '00100', '01000', '10000'),
}


def block_title(text):
    """Render *text* as five rows of block characters.

    Raises ValueError (or KeyError) for a character the font does not cover.
    Callers that cannot trust their input should use ``title_banner``.
    """
    # `Ё` is folded into `Е`: a 5x5 dot pair is not readable enough.
    text = str(text).upper().replace('Ё', 'Е')
    unsupported = sorted(set(char for char in text if char not in BLOCK_FONT))
    if unsupported:
        raise ValueError('unsupported banner characters: %r' % ''.join(unsupported))

    pixels = ['0'.join(BLOCK_FONT[letter][row] for letter in text)
              for row in range(5)]
    width = len(pixels[0]) + 1
    lines = []
    for y in range(5):
        row = []
        for x in range(width):
            solid = x < width - 1 and pixels[y][x] == '1'
            shadow = y > 0 and x > 0 and pixels[y - 1][x - 1] == '1'
            row.append('█' if solid else '░' if shadow else ' ')
        lines.append(''.join(row))
    return lines


def _shadow_row(last_row):
    """Return the drop-shadow row that sits just below a block title."""
    return ''.join('░' if column > 0 and last_row[column - 1] == '█' else ' '
                   for column in range(len(last_row)))


def title_banner(text=DEFAULT_TITLE, width=80):
    """Render the header art with *text* beside it.

    A title that fits is drawn as a block title on the first five rows. A title
    that is too long, or contains characters outside the font, degrades to a
    plain row at the bottom instead of failing. Output never exceeds *width*.
    """
    name = str(text).strip() if text is not None else ''
    if not name:
        name = DEFAULT_TITLE
    width = max(0, int(width))

    art = [line[3:] for line in HEADER_ART]
    art_width = max(map(len, art))
    title_x = art_width + 3

    try:
        block = block_title(name)
    except (KeyError, ValueError):
        block = None

    labels = {}
    # Block rows already reserve a trailing column for the shadow.
    block_width = len(block[0]) if block else 0
    if block and title_x + block_width <= width:
        labels.update(enumerate(block))
        labels[5] = _shadow_row(block[-1])
    elif name == DEFAULT_TITLE:
        # Preserve the original compact brand when the full default title
        # cannot fit, while still showing the full name underneath.
        compact = block_title('VAD-OS')
        if title_x + len(compact[0]) <= width:
            labels.update(enumerate(compact))
        labels[5] = DEFAULT_TITLE
    else:
        labels[5] = name

    return [(line.ljust(title_x) + labels.get(row, ''))[:width]
            for row, line in enumerate(art)]
