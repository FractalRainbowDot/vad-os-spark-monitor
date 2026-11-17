#!/usr/bin/env python3
"""Build the release archives: one per operating system plus the universal one.

Usage:
    python3 build.py            # writes dist/ and refreshes spark-monitor.pyz
    python3 build.py --out out  # custom output directory

Each archive carries the same code; only the packaging is platform-specific:
POSIX archives get the /usr/bin/env python3 shebang and can be executed
directly, the Windows archive has no shebang and is started as
`python spark-monitor-windows.pyz`.  A build-info.json inside every archive
records which asset it is.
"""

import argparse
import hashlib
import json
import pathlib
import shutil
import zipapp

from updater import ASSETS, UNIVERSAL_ASSET, VERSION

PACKAGE_FILES = (
    '__main__.py', 'credentials.py', 'litellm_usage.py', 'discovery.py', 'hosts.py',
    'settings.py', 'updater.py', 'banner.py', 'preferences.py', 'platform_utils.py',
    'themes.py', 'README.md', 'LICENSE',
)

POSIX_INTERPRETER = '/usr/bin/env python3'

# (platform label, release asset name)
ARTIFACTS = (
    ('windows', ASSETS['win32']),
    ('linux', ASSETS['linux']),
    ('macos', ASSETS['darwin']),
)


def stage(directory, root, name, platform):
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    for filename in PACKAGE_FILES:
        shutil.copy2(root / filename, directory / filename)
    info = {'asset': name, 'platform': platform, 'version': VERSION}
    (directory / 'build-info.json').write_text(
        json.dumps(info, indent=2) + '\n', encoding='utf-8')


def checksum(target):
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_name(target.name + '.sha256').write_text(
        f'{digest}  {target.name}\n', encoding='utf-8')
    return digest


def build(out):
    root = pathlib.Path(__file__).resolve().parent
    out = pathlib.Path(out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)
    built = []
    for platform, name in ARTIFACTS:
        staging = out / ('.build-' + platform)
        stage(staging, root, name, platform)
        try:
            zipapp.create_archive(
                str(staging), str(out / name),
                interpreter=None if platform == 'windows' else POSIX_INTERPRETER,
                compressed=True)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        built.append((out / name, checksum(out / name)))
    staging = out / '.build-universal'
    stage(staging, root, UNIVERSAL_ASSET, 'any')
    try:
        zipapp.create_archive(str(staging), str(root / UNIVERSAL_ASSET),
                              interpreter=POSIX_INTERPRETER, compressed=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    built.append((root / UNIVERSAL_ASSET, checksum(root / UNIVERSAL_ASSET)))
    for path, digest in built:
        print(f'{digest}  {path.name}')
    return built


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='dist', help='output directory for OS assets')
    build(parser.parse_args().out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
