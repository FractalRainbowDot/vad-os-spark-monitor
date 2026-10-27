"""Read-only inference discovery on the configured Spark hosts, via SSH."""

import ipaddress
import json
import subprocess


PROBE = r'''
import concurrent.futures, json, re, subprocess, urllib.request
from pathlib import Path

class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

endpoints = set()
labels = {}
def add(address, port, label='', allow_any=False):
    address = address.strip('[]')
    if address in ('0.0.0.0', '::', '*'):
        address = '127.0.0.1'
    if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', address):
        return
    port = int(port)
    if port in (22, 53, 631, 5432) or not 1 <= port <= 65535:
        return
    if not allow_any and port not in http_ports:
        return
    endpoints.add((address, port))
    if label:
        labels[address, port] = label

# Only probe likely HTTP listeners. In particular, never send HTTP to random
# NCCL / distributed-worker sockets on private interfaces.
http_ports = {8000, 8001, 8080, 8081, 9000, 9001}
processes = []
for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        command = path.read_bytes().replace(b'\0', b' ').decode('utf-8', 'replace')
        if any(marker in command.lower() for marker in ('vllm', 'gb10_inference')):
            ports = [int(port) for port in re.findall(
                r'--(?:port|metrics-port|http-port)(?:=|\s+)(\d+)\b', command)]
            http_ports.update(ports)
            # A server without an explicit port listens on the vLLM default.
            if not ports:
                ports = [8000]
            host = re.search(r'--host(?:=|\s+)([^\s]+)', command)
            host = host.group(1).strip('"\'') if host else '0.0.0.0'
            threads = None
            try:
                status = path.parent.joinpath('status').read_text(errors='replace')
                match = re.search(r'^Threads:\s*(\d+)', status, re.M)
                threads = int(match.group(1)) if match else None
            except OSError:
                pass
            capacity = re.search(r'--(?:max-num-seqs|max-batch)(?:=|\s+)(\d+)\b', command)
            # One record per port keeps metadata available for every endpoint
            # the same process exposes (engine, metrics and HTTP ports differ).
            for port in dict.fromkeys(ports):
                processes.append({
                    'host': host,
                    'port': port,
                    'threads': threads,
                    'capacity': int(capacity.group(1)) if capacity else None,
                })
    except OSError:
        pass

def process_metadata(endpoint):
    address, port = endpoint
    candidates = [item for item in processes if item['port'] == port]
    for item in candidates:
        if item['host'] == address:
            return item
    for item in candidates:
        if item['host'] in ('0.0.0.0', '::', '*') or address in ('127.0.0.1', '::1'):
            return item
    return {}
listeners = subprocess.run(['ss', '-H', '-ltn'], capture_output=True, text=True, timeout=3)
if listeners.returncode:
    raise RuntimeError('Cannot list listening ports')
for line in listeners.stdout.splitlines():
    try:
        address, port = line.split()[3].rsplit(':', 1)
        if int(port) in http_ports:
            add(address, port)
    except (ValueError, IndexError):
        pass

# Published ports come from ss. Also inspect unpublished bridge endpoints;
# inspect only the port/network metadata, never secrets in container env.
docker_ok = False
try:
    p = subprocess.run(['docker', 'ps', '-q'], capture_output=True, text=True, timeout=3)
    if p.returncode == 0:
        docker_ok = True
        ids = p.stdout.split()[:64]
        for identifier in ids:
            p = subprocess.run(['docker', 'inspect', '--format',
                '{{json .NetworkSettings}}', identifier], capture_output=True, text=True, timeout=2)
            if p.returncode:
                docker_ok = False
                continue
            settings = json.loads(p.stdout)
            for spec, bindings in (settings.get('Ports') or {}).items():
                if not spec.endswith('/tcp'):
                    continue
                internal = int(spec.split('/')[0])
                for binding in bindings or []:
                    # A published port is an intentional host exposure, so a
                    # custom port is safe to probe. Unpublished bridge ports are
                    # limited to known HTTP ports to avoid NCCL/worker sockets.
                    add(binding['HostIp'], binding['HostPort'], allow_any=True)
                if not bindings and internal in http_ports:
                    for network in (settings.get('Networks') or {}).values():
                        if network.get('IPAddress'):
                            add(network['IPAddress'], internal, identifier[:12])
except (OSError, ValueError, subprocess.TimeoutExpired):
    docker_ok = False

def probe(endpoint):
    address, port = endpoint
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())
    base = 'http://%s:%s' % endpoint
    try:
        with http.open(base + '/metrics', timeout=1) as response:
            text = response.read(4000000).decode('utf-8', 'replace')
        if re.search(r'^vllm:', text, re.M):
            kind = 'vllm'
        elif re.search(r'^velogb10_', text, re.M):
            kind = 'gb10'
        else:
            return None
    except Exception:
        return None
    names = []
    try:
        with http.open(base + '/v1/models', timeout=1) as response:
            models = json.loads(response.read(1000000)).get('data', [])
        names = [m['id'] for m in models if isinstance(m.get('id'), str)]
    except Exception:
        pass
    if not names:
        names = sorted(set(re.findall(r'\bmodel_name="([^"\n]+)"', text)))
    name = ', '.join(names) or labels.get(endpoint) or 'Inference'
    if any('embed' in n.lower() or 'bge-' in n.lower() or 'e5-' in n.lower() for n in names):
        kind = 'embedding'
    item = {'address': address, 'port': port, 'name': name[:240], 'kind': kind}
    metadata = process_metadata(endpoint)
    if metadata.get('capacity') is not None:
        item['capacity'] = metadata['capacity']
    if metadata.get('threads') is not None:
        item['threads'] = metadata['threads']
    return item

# Prefer loopback: host-network services often also bind a private interface.
ordered = sorted(endpoints, key=lambda e: (e[0] != '127.0.0.1', e[1], e[0]))
limited = len(ordered) > 128
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
    found = [item for item in pool.map(probe, ordered[:128]) if item]
unique = {}
for item in found:
    # Only collapse identical names on the same port; separate replicas on
    # different ports remain separate cards.
    key = (item['name'], item['kind'], item['port'])
    unique.setdefault(key, item)
print(json.dumps({'models': list(unique.values()), 'docker_ok': docker_ok,
                  'limited': limited}))
'''


def discover(host, user):
    try:
        result = subprocess.run([
            'ssh', '-T', '-S', 'none', '-o', 'ControlMaster=no',
            '-o', 'ControlPersist=no', '-o', 'ForkAfterAuthentication=no',
            '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
            '-o', 'ServerAliveInterval=2', '-o', 'ServerAliveCountMax=1',
            '-l', user, host, 'python3 -',
        ], input=PROBE, text=True, capture_output=True, timeout=25)
        if result.returncode:
            return {'error': 'SSH/опрос недоступен', 'models': []}
        data = json.loads(result.stdout)
        for model in data['models']:
            model['host'] = host
            # Only the remote address and port are used for forwarding;
            # names are display data, never shell arguments.
            import ipaddress
            ipaddress.IPv4Address(model['address'])
            if model['kind'] not in ('vllm', 'gb10', 'embedding') or not 1 <= model['port'] <= 65535:
                raise ValueError('Invalid endpoint')
        return data
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return {'error': 'SSH/опрос недоступен', 'models': []}


def endpoint_id(model):
    return model['host'], model['address'], model['port']


def reconcile(models, host, snapshot, create, close):
    """Apply a successful snapshot. Failed probes never erase live cards."""
    if snapshot.get('error'):
        return
    found = {endpoint_id(item): item for item in snapshot['models']}
    for model in models:
        if model.get('host') != host or not model.get('automatic'):
            continue
        descriptor = found.pop(model['endpoint'], None)
        if descriptor is None:
            model.update(status='НЕТ СВЕЖИХ ДАННЫХ: сервер больше не обнаружен',
                         ready=True, missing=True, pending=None)
            close(model)
            continue
        changed = model.get('identity') != (descriptor['name'], descriptor['kind'])
        if changed or model.get('missing') or model['tunnel'].poll() is not None:
            # Create first: a failed reconnect must not destroy a working card.
            try:
                replacement = create(descriptor)
            except Exception:
                model.update(status='НЕТ СВЕЖИХ ДАННЫХ: переподключение не удалось',
                             ready=True, pending=None)
                continue
            close(model)
            model.clear()
            model.update(replacement)
        else:
            # A probe miss is temporary: keep the last known values.
            if 'capacity' in descriptor:
                model['capacity'] = descriptor['capacity']
            if 'threads' in descriptor:
                model['threads'] = descriptor['threads']
    for descriptor in found.values():
        try:
            models.append(create(descriptor))
        except Exception:
            continue
