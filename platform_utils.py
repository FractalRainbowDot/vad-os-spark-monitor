"""Small cross-platform helpers for Linux, macOS and native Windows."""

import os
import stat
import subprocess


def is_windows():
    return os.name == 'nt'


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
