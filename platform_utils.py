"""Small cross-platform helpers for Linux, macOS and native Windows."""

import importlib
import os
import stat
import subprocess
import sys


def is_windows():
    return os.name == 'nt'


def in_virtualenv():
    """True inside a venv, where pip refuses --user installs."""
    return (sys.prefix != getattr(sys, 'base_prefix', sys.prefix)
            or bool(os.environ.get('VIRTUAL_ENV')))


def curses_available():
    try:
        import curses  # noqa: F401 - imported only to check availability
    except ImportError:
        return False
    return True


def install_windows_curses(timeout=300):
    """Fetch the windows-curses wheel with pip; True when curses becomes usable.

    Windows Python ships without curses, so a fresh checkout has no TUI.  The
    package is dependency plumbing rather than application code: it is
    installed once into the user site (or the active venv) and then reused.
    """
    if not is_windows():
        return False
    command = [sys.executable, '-m', 'pip', 'install', '--upgrade',
               '--disable-pip-version-check']
    if not in_virtualenv():
        command.append('--user')
    command.append('windows-curses')
    try:
        completed = subprocess.run(command, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    if completed.returncode != 0:
        return False
    importlib.invalidate_caches()
    return curses_available()


def read_flags():
    """Flags for a read-only, no-follow open where the platform supports them."""
    flags = os.O_RDONLY
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    flags |= getattr(os, 'O_NONBLOCK', 0)
    return flags


def is_regular(info):
    return stat.S_ISREG(info.st_mode)


def owned_by_current_user(info):
    """Windows does not expose Unix uid ownership; ACLs handle that there."""
    if is_windows():
        return True
    getuid = getattr(os, 'getuid', None)
    return getuid is not None and info.st_uid == getuid()


def secure_fd(fd):
    """Restrict a newly created Unix file; Windows ACLs are set after replace."""
    if is_windows():
        return
    fchmod = getattr(os, 'fchmod', None)
    if fchmod is not None:
        fchmod(fd, 0o600)


def secure_file(path):
    """Make a key/config file owner-only using chmod or a Windows ACL."""
    path = str(path)
    if is_windows():
        user = os.environ.get('USERNAME') or os.environ.get('USER')
        if not user:
            return
        try:
            subprocess.run(
                ['icacls', path, '/inheritance:r', '/grant:r', f'{user}:F'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            # The install location is normally %LOCALAPPDATA%, already user-only.
            pass
    else:
        os.chmod(path, 0o600)
