"""Update notification and opt-out automatic replacement from GitHub Releases.

The program never sends credentials. Only a public release asset is downloaded
over HTTPS, its published SHA-256 is verified, and the archive is replaced
atomically in the same directory so the adjacent .env is never touched.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

VERSION = '1.8.1'
REPO = 'FractalRainbowDot/vad-os-spark-monitor'
# One archive per operating system, selected at download time.  The universal
# name stays published so older installations keep updating.
ASSETS = {
    'win32': 'spark-monitor-windows.pyz',
    'linux': 'spark-monitor-linux.pyz',
    'darwin': 'spark-monitor-macos.pyz',
}
UNIVERSAL_ASSET = 'spark-monitor.pyz'
MAX_DOWNLOAD = 16 * 1024 * 1024
USER_AGENT = 'VAD-OS-Spark-Monitor/' + VERSION


def platform_asset(platform=None):
    """Release asset for this OS; unknown platforms use the universal archive."""
    platform = sys.platform if platform is None else platform
    return ASSETS.get(platform, UNIVERSAL_ASSET)


def version_tuple(text):
    match = re.fullmatch(r'v?(\d+(?:\.\d+)*)', str(text).strip())
    if not match:
        return None
    return tuple(int(part) for part in match[1].split('.'))


def is_newer(remote, current=VERSION):
    left, right = version_tuple(remote), version_tuple(current)
    if left is None or right is None:
        return False
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def _open(url, timeout):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT,
                                                   'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(request, timeout=timeout)


def _release(repo, timeout, asset=None):
    with _open(f'https://api.github.com/repos/{repo}/releases/latest', timeout) as response:
        payload = json.loads(response.read(1000000))
    if not isinstance(payload, dict):
        raise ValueError('GitHub: неожиданный ответ')
    assets = {item.get('name'): item for item in payload.get('assets') or []
              if isinstance(item, dict)}
    names = [asset] if asset else [UNIVERSAL_ASSET]
    if UNIVERSAL_ASSET not in names:
        # A release without the OS-specific archive still keeps older clients
        # and unusual platforms up to date.
        names.append(UNIVERSAL_ASSET)
    selected = None
    for name in names:
        candidate = assets.get(name)
        if candidate is not None and isinstance(candidate.get('browser_download_url'), str):
            selected = candidate
            break
    if selected is None:
        raise ValueError('GitHub: релиз не содержит сборку для этой системы')
    checksum = None
    digest = str(selected.get('digest') or '')
    if digest.startswith('sha256:'):
        checksum = digest.split(':', 1)[1]
    checksum_asset = assets.get(selected['name'] + '.sha256')
    if checksum_asset is None and checksum is not None:
        return payload, selected, checksum
    if checksum_asset is None:
        return payload, selected, None
    with _open(checksum_asset['browser_download_url'], timeout) as response:
        text = response.read(4096).decode('utf-8', 'replace')
    published = text.split()[0].lower() if text.split() else ''
    if len(published) != 64 or any(c not in '0123456789abcdef' for c in published):
        return payload, selected, None
    if checksum is not None and checksum.lower() != published:
        return payload, selected, None
    return payload, selected, published


def _download(asset, checksum, directory, timeout):
    expected = checksum.lower()
    handle, temporary = tempfile.mkstemp(prefix='.spark-monitor-update-', suffix='.pyz',
                                         dir=directory)
    try:
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(handle, 'wb') as output, _open(asset['browser_download_url'], timeout) as source:
            while block := source.read(1024 * 1024):
                size += len(block)
                if size > MAX_DOWNLOAD:
                    raise ValueError('GitHub: файл обновления слишком большой')
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest() != expected:
            raise ValueError('GitHub: SHA-256 обновления не совпал')
        try:
            archive = zipfile.ZipFile(temporary)
        except zipfile.BadZipFile:
            raise ValueError('GitHub: файл не является программой монитора') from None
        with archive:
            names = archive.namelist()
            if '__main__.py' not in names or archive.testzip() is not None:
                raise ValueError('GitHub: файл не является программой монитора')
            if any(name.startswith(('/', '../')) or '/../' in name for name in names):
                raise ValueError('GitHub: небезопасная структура архива')
        os.chmod(temporary, 0o755)
        return temporary
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def install(archive, candidate):
    archive = Path(archive).resolve()
    if not archive.name.endswith('.pyz') or not archive.is_file():
        raise ValueError('Обновление возможно только для файла .pyz')
    backup = archive.with_name(archive.name + '.prev')
    shutil.copy2(archive, backup)
    try:
        os.replace(candidate, archive)
    except OSError:
        # Keep the original; the backup is identical, but remove it to avoid
        # implying a successful update.
        if backup.exists():
            backup.unlink()
        raise
    return backup


def perform_update(archive=None, current=VERSION, repo=REPO, timeout=6, asset=None):
    """Return {'status': current|updated|available|unavailable|error, ...}."""
    if archive is None:
        return {'status': 'unavailable'}
    try:
        payload, selected, checksum = _release(repo, timeout, asset or platform_asset())
        remote = payload.get('tag_name')
        if not is_newer(remote, current):
            return {'status': 'current', 'version': current}
        url = selected['browser_download_url']
        if checksum is None:
            # Never replace a program without a verifiable checksum.
            return {'status': 'available', 'version': str(remote).lstrip('v'), 'url': url}
        directory = str(Path(archive).resolve().parent)
        candidate = _download(selected, checksum, directory, timeout)
        try:
            install(archive, candidate)
        finally:
            if os.path.exists(candidate):
                os.unlink(candidate)
        return {'status': 'updated', 'version': str(remote).lstrip('v')}
    except urllib.error.HTTPError as exc:
        return {'status': 'error', 'error': f'GitHub HTTP {exc.code}'}
    except (urllib.error.URLError, TimeoutError):
        return {'status': 'error', 'error': 'нет связи с GitHub'}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {'status': 'error', 'error': str(exc)}


def should_recheck(state):
    """Whether periodic polling can still learn something useful."""
    status = (state or {}).get('status')
    return status not in ('updated', 'available', 'unavailable')


def notice(state):
    """One concise line for the dashboard, or None when nothing is relevant."""
    status = (state or {}).get('status')
    if status == 'updated':
        return f"Обновлено до {state['version']} · перезапустите монитор"
    if status == 'available':
        return f"Доступна версия {state['version']} · обновление не установлено"
    return None


def version_badge(state):
    """Short marker next to the running version, or an empty string."""
    status = (state or {}).get('status')
    if status not in ('updated', 'available'):
        return ''
    version = str((state or {}).get('version') or '').lstrip('v')
    if not version:
        return ''
    return '↑ v' + version
