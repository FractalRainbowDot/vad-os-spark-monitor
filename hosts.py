"""Find Spark machines on the user's own Tailscale network.

No cluster addresses are stored in the program or in the repository. The
peer list comes from the local Tailscale client (Tailscale already knows the
addresses), and only online Linux peers whose names match a Spark pattern are
used. SSH access remains the user's own responsibility.
"""

import ipaddress
import json
import re
import shutil
import subprocess

DEFAULT_PATTERN = r'(?:^|[-_])spark(?:[-_]|$|\d)'
MACOS_TAILSCALE = '/Applications/Tailscale.app/Contents/MacOS/Tailscale'


def tailscale_binary():
    return shutil.which('tailscale') or (MACOS_TAILSCALE if shutil.which(MACOS_TAILSCALE) else None)


def discover_hosts(pattern=DEFAULT_PATTERN, timeout=6):
    """Return (hosts, error). A host is {'name': ..., 'ip': IPv4 string}."""
    binary = tailscale_binary()
    if not binary:
        return [], ('Tailscale CLI не найден. Установите Tailscale или укажите --host вручную '
                    '(тогда потребуется --no-discovery).')
    try:
        proc = subprocess.run([binary, 'status', '--json'], capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return [], 'Не удалось получить список машин Tailscale'
    try:
        payload = json.loads(proc.stdout)
    except (ValueError, TypeError):
        return [], 'Tailscale не вернул список машин (проверьте вход в tailnet)'
    peers = payload.get('Peer') or {}
    if not isinstance(peers, dict):
        return [], 'Tailscale вернул неожиданный формат списка машин'
    try:
        wanted = re.compile(pattern, re.I)
    except re.error:
        return [], 'Некорректный шаблон имён Spark'
    hosts = {}
    for peer in peers.values():
        if not isinstance(peer, dict) or not peer.get('Online'):
            continue
        if peer.get('OS') not in (None, 'linux'):
            continue
        name = peer.get('HostName') or str(peer.get('DNSName') or '').split('.')[0]
        if not name or not wanted.search(name):
            continue
        addresses = []
        for address in peer.get('TailscaleIPs') or []:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            if parsed.version == 4:
                addresses.append(str(parsed))
        if addresses:
            hosts[name] = addresses[0]
    if not hosts:
        return [], ('В tailnet не найдены включённые машины Spark. '
                    'Измените шаблон --spark-pattern или укажите --host.')
    return [{'name': name, 'ip': ip} for name, ip in sorted(hosts.items())], None
