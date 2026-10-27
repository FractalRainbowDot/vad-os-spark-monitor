"""Owner-only .env persistence, without executing shell expressions."""

import os
from pathlib import Path
import stat
import tempfile


def key_path():
    archive = getattr(__loader__, 'archive', None)
    if archive:
        return Path(archive).resolve().parent / '.env'
    return Path(__file__).resolve().parent / '.env'


def validate_key(value):
    value = value.strip()
    if not value or len(value) > 4096 or any(c.isspace() or not c.isprintable() for c in value):
        raise ValueError('Нужен непустой API-ключ без пробелов и переносов строк')
    return value


def save_api_key(value, path=None):
    value = validate_key(value)
    path = Path(path) if path is not None else key_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lines = []
    try:
        previous = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        pass
    else:
        with os.fdopen(previous, 'r', encoding='utf-8') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError('Файл .env должен принадлежать текущему пользователю')
            text = stream.read(16385)
            if len(text) > 16384:
                raise ValueError('Файл .env слишком большой')
            for line in text.splitlines():
                entry = line.strip()
                if entry.startswith('export '):
                    entry = entry[7:].lstrip()
                if entry.partition('=')[0].strip() != 'LITELLM_API_KEY':
                    lines.append(line)
    lines.append('LITELLM_API_KEY=' + value)
    fd, temporary = tempfile.mkstemp(prefix='.api-key-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write('\n'.join(lines) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_api_key(path=None):
    environment = os.environ.get('LITELLM_API_KEY', '').strip()
    if environment:
        return validate_key(environment)
    path = Path(path) if path is not None else key_path()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return ''
    with os.fdopen(fd, 'r', encoding='utf-8') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('Файл ключа должен быть обычным файлом текущего пользователя')
        if info.st_mode & 0o077:
            raise ValueError(f'У файла ключа слишком широкие права. Выполните: chmod 600 "{path}"')
        text = stream.read(16385)
        if len(text) > 16384:
            raise ValueError('Файл .env слишком большой')
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('export '):
                line = line[7:].lstrip()
            name, separator, value = line.partition('=')
            if separator and name.strip() == 'LITELLM_API_KEY':
                value = value.strip()
                if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                return validate_key(value)
        raise ValueError('В .env отсутствует LITELLM_API_KEY; используйте --save-key')
