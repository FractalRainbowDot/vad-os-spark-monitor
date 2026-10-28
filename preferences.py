"""Owner-only adjacent preferences for future TUI settings.

Only the allow-listed keys ``theme``, ``display_name`` and ``card_order`` are
read or written. The file is stored next to the running program, is never
shared, and is written atomically with mode 600.
"""

import errno
import json
import os
from pathlib import Path
import stat
import tempfile


CONFIG_NAME = '.spark-monitor.json'
MAX_SIZE = 16384
MAX_DISPLAY_NAME = 32
MAX_CARD_ORDER = 128
MAX_CARD_KEY = 320
_ALLOWED = ('theme', 'display_name', 'card_order')


def config_path():
    archive = getattr(__loader__, 'archive', None)
    if archive:
        return Path(archive).resolve().parent / CONFIG_NAME
    return Path(__file__).resolve().parent / CONFIG_NAME


def _sanitize(key, value):
    value = ''.join(char for char in value if char.isprintable()).strip()
    if key == 'display_name':
        value = value[:MAX_DISPLAY_NAME]
    elif key == 'card_order':
        value = value[:MAX_CARD_KEY]
    return value


def _sanitize_card_order(value):
    if not isinstance(value, list):
        return []
    result, seen = [], set()
    for item in value:
        if not isinstance(item, str):
            continue
        item = _sanitize('card_order', item)
        if item and item not in seen:
            result.append(item)
            seen.add(item)
        if len(result) >= MAX_CARD_ORDER:
            break
    return result


def load_preferences(path=None):
    """Return saved theme and display name, or an empty dict when absent.

    Unknown keys, non-string values, and values that become empty after
    sanitizing are omitted. A symlink, a non-regular file, or a file owned by
    another user is rejected.
    """
    path = Path(path) if path is not None else config_path()
    try:
        handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {}
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ValueError('Файл настроек не должен быть символической ссылкой') from None
        raise
    with os.fdopen(handle, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('Файл настроек должен быть обычным файлом текущего пользователя')
        data = stream.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise ValueError('Файл настроек слишком большой')
    try:
        payload = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError('Файл настроек содержит некорректный JSON') from None
    if not isinstance(payload, dict):
        raise ValueError('Файл настроек должен содержать объект JSON')
    result = {}
    for key in _ALLOWED:
        value = payload.get(key)
        if key == 'card_order':
            order = _sanitize_card_order(value)
            if order:
                result[key] = order
        elif isinstance(value, str):
            value = _sanitize(key, value)
            if value:
                result[key] = value
    return result


def save_preferences(values, path=None):
    """Atomically write the given allowed keys with mode 600.

    Only allow-listed values are written. Existing values are not merged, so
    callers should pass the current values when changing one of them. Empty
    values and malformed card order entries are omitted.
    """
    if not isinstance(values, dict):
        raise ValueError('Ожидается словарь настроек')
    path = Path(path) if path is not None else config_path()
    result = {}
    for key in _ALLOWED:
        value = values.get(key)
        if key == 'card_order':
            order = _sanitize_card_order(value)
            if order:
                result[key] = order
        elif isinstance(value, str):
            value = _sanitize(key, value)
            if value:
                result[key] = value
    payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle, temporary = tempfile.mkstemp(prefix='.spark-monitor-', suffix='.json',
                                         dir=path.parent)
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            handle = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # os.replace does not follow a symlink at the destination.
        os.replace(temporary, path)
    finally:
        if handle != -1:
            os.close(handle)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
