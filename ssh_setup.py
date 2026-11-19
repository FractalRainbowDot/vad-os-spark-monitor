"""Interactive SSH onboarding, before curses takes over the terminal.

Passwords and host-key confirmation belong to the native SSH client. Never
capture its interactive output or disable host verification.
"""

from pathlib import Path
import shlex
import shutil
import subprocess


def probe(ssh, host, user):
    result = subprocess.run(
        [ssh, '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
         '-o', 'ConnectTimeout=5', '-l', user, host, 'true'],
        capture_output=True, text=True, timeout=10, check=False)
    return result.returncode == 0, result.stderr.strip()


def confirm(message):
    return input(message + ' [y/N]: ').strip().lower() in ('y', 'yes', 'д', 'да')


def public_key():
    """Use an existing default key, or generate one with explicit permission."""
    directory = Path.home() / '.ssh'
    for name in ('id_ed25519', 'id_rsa', 'id_ecdsa'):
        private = directory / name
        public = directory / (name + '.pub')
        if private.is_file() and public.is_file():
            value = public.read_text(encoding='utf-8').strip()
            if '\n' not in value and value.startswith(('ssh-', 'ecdsa-')):
                return value
    private = directory / 'id_ed25519'
    if private.exists() or private.with_suffix('.pub').exists():
        print('Нет пары ключей id_ed25519 / id_ed25519.pub. Существующие файлы не изменены.')
        return None
    if not confirm('Создать SSH-ключ на этом компьютере для входа на Spark?'):
        return None
    keygen = shutil.which('ssh-keygen')
    if not keygen:
        print('Не найден ssh-keygen. Установите OpenSSH Client.')
        return None
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    print('ssh-keygen спросит passphrase. Для автоматического входа с passphrase нужен ssh-agent.')
    result = subprocess.run(
        [keygen, '-t', 'ed25519', '-f', str(private)], check=False)
    if result.returncode:
        return None
    return private.with_suffix('.pub').read_text(encoding='utf-8').strip()


def install_command(key):
    # Only the public key is passed as an argument. Never send a private key.
    line = shlex.quote(key)
    return (
        'umask 077; mkdir -p ~/.ssh && '
        'touch ~/.ssh/authorized_keys && '
        'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && '
        f'(grep -qxF -- {line} ~/.ssh/authorized_keys || '
        f"printf '%s\\n' {line} >> ~/.ssh/authorized_keys)"
    )


def prepare_ssh(hosts, user, ssh):
    """Return whether startup may continue; never configure hosts silently."""
    try:
        for host in hosts:
            address = host['ip']
            name = host.get('name', address)
            try:
                ready, error = probe(ssh, address, user)
            except (OSError, subprocess.SubprocessError) as exc:
                ready, error = False, str(exc)
            if ready:
                continue
            print(f'\nSSH: {name} ({address}), пользователь {user}\n{error}')
            if not confirm('Настроить подключение в этом окне?'):
                continue
            print('SSH покажет отпечаток сервера: сверьте его с администратором.')
            print('Если ключ сервера изменился, проверка НЕ будет отключена.')
            print('Введите пароль сервера при запросе. Монитор его не сохраняет.')
            result = subprocess.run(
                [ssh, '-T', '-o', 'BatchMode=no',
                 '-o', 'StrictHostKeyChecking=ask', '-o', 'ConnectTimeout=10',
                 '-l', user, address, 'true'], check=False)
            if result.returncode:
                print('Вход не выполнен. Настройка этого сервера пропущена.')
                continue
            # Host-key acceptance alone may have restored agent/key access.
            ready, _ = probe(ssh, address, user)
            if ready:
                continue
            if not confirm('Добавить публичный SSH-ключ в ~/.ssh/authorized_keys на этом сервере?'):
                continue
            key = public_key()
            if not key:
                continue
            result = subprocess.run(
                [ssh, '-T', '-o', 'BatchMode=no',
                 '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
                 '-l', user, address, install_command(key)], check=False)
            ready, _ = probe(ssh, address, user)
            if result.returncode == 0 and ready:
                print(f'{name}: вход без пароля настроен.')
            else:
                print('Автоматический вход пока недоступен. Проверьте ключ/ssh-agent и права на сервере.')
        return True
    except (EOFError, KeyboardInterrupt):
        print('\nНастройка отменена.')
        return False
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f'Ошибка настройки SSH: {exc}')
        return False
