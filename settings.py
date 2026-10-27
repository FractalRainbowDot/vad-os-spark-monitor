"""Read-only static launch configuration of inference servers on each Spark.

Only command lines and container metadata are read. Container environment is
never requested, and credential-like flags are redacted before display.
"""

import json
import re
import subprocess
import textwrap

SENSITIVE = ('--api-key', '--token', '--hf-token', '--password', '--secret')
INFERENCE = re.compile(r'vllm|deepseek|qwen|sglang|inference|llama', re.I)


PROBE = r'''
import json, re, subprocess
from pathlib import Path

SENSITIVE = ('--api-key', '--token', '--hf-token', '--password', '--secret')
INFERENCE = re.compile(r'vllm|deepseek|qwen|sglang|inference|llama', re.I)

def clean(value):
    value = re.sub(r'(://[^/@\s]+)@', '://<REDACTED>@', value)
    if re.fullmatch(r'(?:sk-|hf_)[A-Za-z0-9_-]{8,}', value):
        return '<REDACTED>'
    return value

def redact(argv):
    result, index = [], 0
    while index < len(argv):
        item = argv[index]
        low = item.lower()
        if any(low == flag or low.startswith(flag + '=') for flag in SENSITIVE):
            if '=' in item:
                result.append(item.split('=', 1)[0] + '=<REDACTED>')
            else:
                result.append(item + '=<REDACTED>')
                if index + 1 < len(argv) and not argv[index + 1].startswith('--'):
                    index += 1
            index += 1
            continue
        result.append(clean(item))
        index += 1
    return result

result = {'containers': [], 'processes': [], 'docker_ok': False}
try:
    p = subprocess.run(['docker', 'ps', '-q'], capture_output=True, text=True, timeout=4)
    if p.returncode == 0:
        result['docker_ok'] = True
        for identifier in p.stdout.split()[:32]:
            q = subprocess.run(['docker', 'inspect', '--format', '{{json .}}', identifier],
                               capture_output=True, text=True, timeout=3)
            if q.returncode:
                continue
            item = json.loads(q.stdout)
            cfg = item.get('Config') or {}
            cmd = (cfg.get('Entrypoint') or []) + (cfg.get('Cmd') or [])
            if not INFERENCE.search(' '.join([item.get('Name', ''), cfg.get('Image', '')] + cmd)):
                continue
            result['containers'].append({
                'name': item.get('Name', '').lstrip('/'),
                'image': cfg.get('Image', ''),
                'cmd': redact(cmd),
                'started': (item.get('State') or {}).get('StartedAt', ''),
                'ports': (item.get('NetworkSettings') or {}).get('Ports') or {},
                'network': item.get('HostConfig', {}).get('NetworkMode', ''),
            })
except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
    pass

for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        argv = path.read_bytes().replace(b'\0', b' ').decode('utf-8', 'replace').split()
        text = ' '.join(argv)
        if not re.search(r'vllm serve|gb10_inference|vllm\.entrypoints', text):
            continue
        if 'python3 -' in text or text.startswith('ssh '):
            continue
        result['processes'].append({'argv': redact(argv)})
    except OSError:
        pass
print(json.dumps(result))
'''


def _run(host, user):
    proc = subprocess.run([
        'ssh', '-T', '-S', 'none', '-o', 'ControlMaster=no',
        '-o', 'ControlPersist=no', '-o', 'ForkAfterAuthentication=no',
        '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
        '-o', 'ServerAliveInterval=2', '-o', 'ServerAliveCountMax=1',
        '-l', user, host, 'python3 -',
    ], input=PROBE, text=True, capture_output=True, timeout=20)
    if proc.returncode:
        raise RuntimeError('SSH/опрос недоступен')
    return json.loads(proc.stdout)


def parse_flags(argv):
    flags, positional = [], []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item.startswith('--'):
            name, separator, value = item.partition('=')
            if separator:
                flags.append((name, value))
            elif index + 1 < len(argv) and not argv[index + 1].startswith('--'):
                flags.append((name, argv[index + 1]))
                index += 1
            else:
                flags.append((name, ''))
        else:
            positional.append(item)
        index += 1
    return flags, positional


def _clean(value):
    value = re.sub(r'(://[^/@\s]+)@', '://<REDACTED>@', value)
    if re.fullmatch(r'(?:sk-|hf_)[A-Za-z0-9_-]{8,}', value):
        return '<REDACTED>'
    return value


def _redact(argv):
    result, index = [], 0
    while index < len(argv):
        item = argv[index]
        low = item.lower()
        if any(low == flag or low.startswith(flag + '=') for flag in SENSITIVE):
            if '=' in item:
                result.append(item.split('=', 1)[0] + '=<REDACTED>')
            else:
                result.append(item + '=<REDACTED>')
                if index + 1 < len(argv) and not argv[index + 1].startswith('--'):
                    index += 1
            index += 1
            continue
        result.append(_clean(item))
        index += 1
    return result


def _first(flags, *names):
    for name in names:
        for flag, value in flags:
            if flag == name:
                return value
    return ''


def _model_name(flags, positional):
    value = _first(flags, '--served-model-name', '--model', '--model-dir')
    if not value:
        value = next((item for item in positional if '/' in item or item not in
                      ('vllm', 'serve', 'python3', '-m', 'vllm.entrypoints.openai.api_server')), '')
    if value.startswith('/') or value.startswith('./'):
        return value.rstrip('/').rsplit('/', 1)[-1]
    return value or 'Inference'


def _engine(argv):
    text = ' '.join(argv)
    if 'gb10_inference' in text:
        return 'gb10'
    if 'vllm' in text:
        return 'vLLM'
    return 'inference'


def _identity(entry):
    flags, positional = parse_flags(entry['argv'])
    return (_model_name(flags, positional), _first(flags, '--port'),
            _first(flags, '--node-rank'))


def entries(raw):
    found = []
    containers = set()
    for container in raw.get('containers') or []:
        cmd = _redact(container.get('cmd') or [])
        flags, positional = parse_flags(cmd)
        item = dict(container, argv=cmd, source='контейнер',
                    engine=_engine(cmd),
                    model=_model_name(flags, positional))
        containers.add(_identity(item))
        found.append(item)
    processes = set()
    for process in raw.get('processes') or []:
        argv = _redact(process.get('argv') or [])
        flags, positional = parse_flags(argv)
        item = dict(process, argv=argv, source='процесс', engine=_engine(argv),
                    model=_model_name(flags, positional), name='', image='',
                    started='', ports={}, network='')
        identity = _identity(item)
        if identity in containers or identity in processes:
            continue
        processes.add(identity)
        found.append(item)
    return found


def read_settings(host, user):
    try:
        raw = _run(host, user)
        return {'entries': entries(raw), 'error': None,
                'docker_ok': bool(raw.get('docker_ok'))}
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        return {'entries': [], 'error': 'SSH/опрос недоступен', 'docker_ok': False}


def _number(value):
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _gib(value):
    try:
        return f'{int(value) / 1024 ** 3:.2f} GiB'
    except (TypeError, ValueError):
        return str(value)


def _summary(config):
    try:
        data = json.loads(config)
    except (TypeError, ValueError):
        return config
    if isinstance(data, dict):
        method = data.get('method')
        tokens = data.get('num_speculative_tokens')
        if method:
            return f'{method} · {tokens} токенов' if tokens else str(method)
        mode = data.get('cudagraph_mode')
        if mode:
            return str(mode)
    return config


def _published(entry):
    for spec, bindings in (entry.get('ports') or {}).items():
        for binding in bindings or []:
            if spec.endswith('/tcp'):
                return f"{binding.get('HostIp', '127.0.0.1')}:{binding.get('HostPort')} → {spec.split('/')[0]}"
    return ''


def curated(entry):
    flags, positional = parse_flags(entry['argv'])
    rows = [('Модель', entry['model']),
            ('Движок', entry['engine']),
            ('Источник', entry['source'] + (' · ' + entry['name'] if entry.get('name') else '')),
            ('Образ', entry.get('image') or '—'),
            ('Запущено', (entry.get('started') or '—').replace('T', ' ').split('.')[0].replace('Z', ' UTC')),
            ('Путь модели', _first(flags, '--model', '--model-dir') or
             next((item for item in positional if item.startswith('/')), '—'))]
    address = _first(flags, '--host') or '127.0.0.1'
    port = _first(flags, '--port')
    published = _published(entry)
    rows.append(('Адрес', published or (address + ':' + port if port else '—')))
    if _first(flags, '--tensor-parallel-size') or _first(flags, '--pipeline-parallel-size'):
        rows.append(('TP / PP', (_first(flags, '--tensor-parallel-size') or '—') + ' / ' +
                     (_first(flags, '--pipeline-parallel-size') or '—')))
    if _first(flags, '--nnodes') or _first(flags, '--node-rank'):
        rows.append(('Узлы / rank', (_first(flags, '--nnodes') or '—') + ' / ' +
                     (_first(flags, '--node-rank') or '—')))
    master = _first(flags, '--master-addr')
    if master:
        rows.append(('Master', master + (':' + _first(flags, '--master-port')
                    if _first(flags, '--master-port') else '')))
    context = _first(flags, '--max-model-len', '--max-seq-len')
    if context:
        rows.append(('Контекст', _number(context)))
    sequences = _first(flags, '--max-num-seqs', '--max-batch')
    if sequences:
        rows.append(('Max seqs / batch', sequences))
    if _first(flags, '--max-num-batched-tokens'):
        rows.append(('Max batched tokens', _first(flags, '--max-num-batched-tokens')))
    if _first(flags, '--gpu-memory-utilization'):
        raw_gpu = _first(flags, '--gpu-memory-utilization')
        try:
            rows.append(('GPU memory', f'{float(raw_gpu) * 100:.0f}%'))
        except ValueError:
            rows.append(('GPU memory', raw_gpu))
    kv = []
    if _first(flags, '--kv-cache-memory-bytes'):
        kv.append(_gib(_first(flags, '--kv-cache-memory-bytes')))
    if _first(flags, '--kv-cache-dtype'):
        kv.append(_first(flags, '--kv-cache-dtype'))
    if _first(flags, '--kv-cache'):
        kv.append(_first(flags, '--kv-cache'))
    if kv:
        rows.append(('KV-cache', ' · '.join(kv)))
    if _first(flags, '--dtype'):
        rows.append(('Dtype', _first(flags, '--dtype')))
    if _first(flags, '--quantization'):
        rows.append(('Квантование', _first(flags, '--quantization')))
    if _first(flags, '--attention-backend'):
        rows.append(('Attention', _first(flags, '--attention-backend')))
    if _first(flags, '--runner'):
        rows.append(('Runner', _first(flags, '--runner')))
    for flag, label in (('--reasoning-effort', 'Reasoning'),
                        ('--ple-ram', 'PLE RAM'),
                        ('--prefill-chunk', 'Prefill chunk'),
                        ('--prefix-tail-ckpt', 'Prefix tail ckpt'),
                        ('--long-prefill-token-threshold', 'Long prefill threshold'),
                        ('--limit-mm-per-prompt', 'Multimodal limit')):
        value = _first(flags, flag)
        if value:
            rows.append((label, value))
    for flag, label in (('--speculative-config', 'Speculative'),
                        ('--compilation-config', 'Compilation'),
                        ('--engram-config', 'Engram'),
                        ('--hf-overrides', 'HF overrides')):
        value = _first(flags, flag)
        if value:
            rows.append((label, _summary(value)))
    parsers = [value for flag, value in flags
               if flag in ('--tool-call-parser', '--reasoning-parser') and value]
    if parsers:
        rows.append(('Parsers', ', '.join(parsers)))
    enabled = [flag[2:] for flag, value in flags
               if flag in ('--enable-chunked-prefill', '--enforce-eager', '--headless',
                           '--enable-auto-tool-choice', '--enable-prompt-tokens-details')
               and not value]
    if enabled:
        rows.append(('Флаги', ', '.join(enabled)))
    return rows


def flag_lines(entry):
    flags, positional = parse_flags(entry['argv'])
    lines = []
    if positional:
        lines.append('команда: ' + ' '.join(positional))
    for flag, value in flags:
        lines.append(flag + ((' ' + value) if value else ' да'))
    return lines


def _wrap(value, width):
    if not value:
        return ['']
    return textwrap.wrap(value, max(8, width), break_long_words=True,
                         break_on_hyphens=False) or ['']


SECRET_KEYS = {
    'key', 'api_key', 'apikey', 'api_key_id', 'secret', 'secret_key',
    'private_key', 'master_key', 'password', 'passwd', 'token', 'auth',
    'access_token', 'refresh_token', 'id_token', 'session_token',
    'bearer_token', 'azure_ad_token', 'auth_token', 'hf_token',
    'client_secret', 'aws_secret_access_key', 'aws_access_key_id',
    'vertex_credentials', 'credentials', 'credential', 'authorization',
    'cookie', 'set_cookie',
}

# Count and cost fields legitimately contain "token". They must stay visible.
SAFE_TOKEN_KEYS = {
    'max_tokens', 'max_input_tokens', 'max_output_tokens',
    'max_completion_tokens', 'max_num_batched_tokens', 'max_batch_tokens',
    'max_context_tokens', 'num_speculative_tokens',
    'prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens',
    'cached_tokens', 'prompt_tokens_details', 'completion_tokens_details',
    'token_budget', 'token_count',
    'input_cost_per_token', 'output_cost_per_token',
    'cache_read_input_token_cost', 'cache_creation_input_token_cost',
    'key_alias', 'tokenizer', 'tokenizer_name', 'tokenizer_config',
    'skip_tokenizer_init', 'tokenizer_mode',
}

SECRET_FRAGMENTS = ('api_key', 'apikey', 'secret', 'password', 'passwd',
                    'credential', 'private_key', 'access_key', 'authorization',
                    'token', 'bearer')
SECRET_AUTH = re.compile(r'(?:^|_)auth(?:_|$)')

_ANSI = re.compile(
    r'\x1b\[[0-?]*[ -/]*[@-~]'
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'
    r'|\x1b[@-_]'
)
_CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
_USERINFO = re.compile(r'://[^/\s]+@')
_QUERY = re.compile(
    r'(?i)([?&;](?:x[_-]?api[_-]?key|api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|'
    r'id[_-]?token|auth[_-]?token|session[_-]?token|bearer[_-]?token|'
    r'token|secret|client[_-]?secret|password|passwd|credential|credentials|'
    r'authorization|auth|signature|sig|key)=)([^&#;\s]*)'
)
_HEADER = re.compile(
    r'(?i)((?<![?&;])\b(?:authorization|proxy-authorization|x-api-key|api-key|'
    r'api_key|x-auth-token|x-goog-api-key|cookie|set-cookie)\s*["\']?\s*[:=]\s*)'
    r'("[^"\r\n]*"|\'[^\'\r\n]*\'|[^,\r\n]+)'
)
_ASSIGN = re.compile(
    r'(?i)\b([A-Za-z][\w.-]*)(\s*["\']?\s*[:=]\s*)'
    r'("[^"]*"|\'[^\']*\'|[^\s,;&?=}]+)'
)
_AUTH = re.compile(
    r'\b((?i:bearer|basic))\s+'
    r'(?=[A-Za-z0-9._~+/=-]{8,})'
    r'(?=[A-Za-z0-9._~+/=-]*(?:[0-9._~+/=-]|[A-Z]))'
    r'[A-Za-z0-9._~+/=-]+'
)
_AUTH_FULL = re.compile(r'(?i:bearer|basic)\s+\S+')
_SECRET_VALUE = re.compile(
    r'(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{8,}'
    r'|hf_[A-Za-z0-9_-]{8,}'
    r'|gsk_[A-Za-z0-9_-]{8,}'
    r'|AIza[A-Za-z0-9_-]{8,}'
    r'|AKIA[A-Z0-9]{8,})'
    r'(?![A-Za-z0-9])'
)


def _normalize_key(name):
    key = _ANSI.sub('', str(name).strip())
    key = _CONTROL.sub('', key)
    key = re.sub(r'\s+', '_', key)
    return key.casefold().replace('-', '_')


def _secret_key(name):
    key = _normalize_key(name)
    if not key:
        return False
    if key in SAFE_TOKEN_KEYS:
        return False
    if key in SECRET_KEYS:
        return True
    return (any(fragment in key for fragment in SECRET_FRAGMENTS) or
            bool(SECRET_AUTH.search(key)))


def _plain_text(value):
    text = str(value)
    text = _ANSI.sub('', text)
    text = _CONTROL.sub('', text)
    text = text.replace('\t', ' ')
    return re.sub(r'[\r\n]+', ' ', text)


def _redact_assignment(match):
    if _secret_key(match.group(1)):
        return match.group(1) + match.group(2) + '<скрыто>'
    return match.group(0)


def _sanitize_text(value):
    text = _plain_text(value)
    text = _USERINFO.sub('://<скрыто>@', text)
    text = _QUERY.sub(lambda match: match.group(1) + '<скрыто>', text)
    if _AUTH_FULL.fullmatch(text.strip()):
        return '<скрыто>'
    text = _AUTH.sub(lambda match: match.group(1) + ' <скрыто>', text)
    if _SECRET_VALUE.fullmatch(text.strip()):
        return '<скрыто>'
    text = _SECRET_VALUE.sub('<скрыто>', text)
    text = _HEADER.sub(lambda match: match.group(1) + '<скрыто>', text)
    return _ASSIGN.sub(_redact_assignment, text)


def _sanitize(value, key='', depth=0):
    if _secret_key(key):
        return '<скрыто>'
    if isinstance(value, dict):
        return {(_plain_text(k) if isinstance(k, str) else k):
                _sanitize(v, k, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v, key, depth + 1) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if depth < 6 and text[:1] in '{[':
            try:
                data = json.loads(text)
            except (TypeError, ValueError):
                pass
            else:
                if isinstance(data, (dict, list)):
                    return _sanitize(data, key, depth + 1)
        return _sanitize_text(value)
    return value


def _provider_value(value, key=''):
    value = _sanitize(value, key)
    if value is None:
        return '—'
    if isinstance(value, bool):
        return 'да' if value else 'нет'
    if isinstance(value, float):
        return f'{value:g}'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return str(value)


def _per_million(value):
    try:
        number = float(value) * 1_000_000
    except (TypeError, ValueError):
        return '—'
    return f'${number:g} / 1M'


def _nonempty(value):
    if value is None or value == [] or value == {}:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def provider_rows(entry):
    params = entry.get('litellm_params') or {}
    info = entry.get('model_info') or {}
    rows = [
        ('Маршрут', _provider_value(entry.get('model_name') or '—')),
        ('Провайдер', _provider_value(params.get('custom_llm_provider') or
                                       info.get('litellm_provider') or '—')),
        ('Upstream', _provider_value(params.get('model') or '—')),
        ('API base', _provider_value(params.get('api_base') or '—')),
    ]
    if _nonempty(info.get('max_input_tokens')) or _nonempty(info.get('max_output_tokens')):
        rows.append(('Вход / выход', _provider_value(info.get('max_input_tokens')) + ' / ' +
                     _provider_value(info.get('max_output_tokens'))))
    if _nonempty(info.get('max_tokens')):
        rows.append(('Max tokens', _provider_value(info.get('max_tokens'))))
    rows.append(('RPM / TPM', _provider_value(info.get('rpm')) + ' / ' +
                 _provider_value(info.get('tpm'))))
    input_cost = params.get('input_cost_per_token')
    output_cost = params.get('output_cost_per_token')
    if input_cost is None:
        input_cost = info.get('input_cost_per_token')
    if output_cost is None:
        output_cost = info.get('output_cost_per_token')
    if input_cost is not None or output_cost is not None:
        rows.append(('Стоимость', _per_million(input_cost) + ' вход · ' +
                     _per_million(output_cost) + ' выход'))
    if _nonempty(info.get('mode')):
        rows.append(('Режим', _provider_value(info['mode'])))
    if info.get('blocked') is not None:
        rows.append(('Заблокирован', _provider_value(info['blocked'])))
    if info.get('direct_access') is not None:
        rows.append(('Direct access', _provider_value(info['direct_access'])))
    for key, label in (('description', 'Описание'), ('access_groups', 'Access groups'),
                       ('pricing_overrides', 'Pricing overrides')):
        if _nonempty(info.get(key)):
            rows.append((label, _provider_value(info[key])))
    for key, label in (('tags', 'Tags'), ('guardrails', 'Guardrails')):
        if _nonempty(params.get(key)):
            rows.append((label, _provider_value(params[key])))
    if _nonempty(info.get('id')):
        rows.append(('ID', _provider_value(info['id'])))
    return rows


def provider_params(entry):
    params = entry.get('litellm_params') or {}
    info = entry.get('model_info') or {}
    items = []
    for key, value in params.items():
        if _nonempty(value):
            items.append((key, value))
    for key, value in info.items():
        if _nonempty(value) and key not in params:
            items.append((key, value))
    return items


def provider_table(entry, width):
    title = 'ПРОВАЙДЕР · ' + _plain_text(entry.get('model_name') or 'model')
    inner = max(20, width - 4)
    rows = []
    for label, value in provider_rows(entry):
        prefix = f'{label:24} │ '
        chunks = _wrap(_provider_value(value), inner - len(prefix))
        rows.append(prefix + chunks[0])
        rows.extend(' ' * len(prefix) + chunk for chunk in chunks[1:])
    rows.append('━ ВСЕ ПАРАМЕТРЫ ПРОВАЙДЕРА')
    for key, value in provider_params(entry):
        line = f'{_plain_text(key)} {_provider_value(value, key)}'
        for index, chunk in enumerate(_wrap(line, inner - 2)):
            rows.append(('  ' if index == 0 else '    ') + chunk)
    return framed_table(title, rows, width)


def provider_document(providers, error, width):
    lines = []
    if error:
        lines.extend(framed_table('ПРОВАЙДЕР · LITELLM /model/info',
                                  ['НЕТ ДАННЫХ: ' + _plain_text(error)], width))
        lines.append('')
    if providers is None:
        if not error:
            lines.extend(framed_table('ПРОВАЙДЕР · LITELLM /model/info',
                                      ['Загрузка параметров провайдера…'], width))
            lines.append('')
    elif not providers:
        lines.extend(framed_table('ПРОВАЙДЕР · LITELLM /model/info',
                                  ['Маршруты провайдера не найдены'], width))
        lines.append('')
    else:
        for entry in providers:
            lines.extend(provider_table(entry, width))
            lines.append('')
    return lines


def settings_table(host, snapshot, width, now=None):
    title = f'{host} · модели: {len(snapshot["entries"])}'
    if snapshot.get('error'):
        return framed_table(title, ['НЕТ СВЕЖИХ ДАННЫХ: ' + snapshot['error']], width)
    if not snapshot['entries']:
        return framed_table(title, ['Модели не найдены'], width)
    inner = max(20, width - 4)
    rows = []
    for position, entry in enumerate(snapshot['entries']):
        if position:
            rows.append('')
        rows.append('━ ' + entry['model'])
        for label, value in curated(entry):
            prefix = f'{label:24} │ '
            chunks = _wrap(value, inner - len(prefix))
            rows.append(prefix + chunks[0])
            rows.extend(' ' * len(prefix) + chunk for chunk in chunks[1:])
        rows.append('━ ВСЕ ФЛАГИ ЗАПУСКА')
        for line in flag_lines(entry):
            for index, chunk in enumerate(_wrap(line, inner - 2)):
                rows.append(('  ' if index == 0 else '    ') + chunk)
    return framed_table(title, rows, width)


def settings_document(hosts, cache, errors, width, now, providers=None,
                      provider_error='', include_provider=False, include_sparks=True):
    lines = []
    if include_provider:
        lines.extend(provider_document(providers, provider_error, width))
    if include_sparks:
        for host in hosts:
            if host['ip'] in errors:
                lines.extend(framed_table(host['name'], ['НЕТ СВЕЖИХ ДАННЫХ: ' + errors[host['ip']]], width))
            elif host['ip'] not in cache:
                lines.extend(framed_table(host['name'], ['Загрузка настроек…'], width))
            else:
                timestamp, snapshot = cache[host['ip']]
                lines.extend(settings_table(host['name'], snapshot, width, now))
            lines.append('')
    return lines


def framed_table(title, rows, width):
    """Kept local to avoid a circular import with the main dashboard."""
    width = max(4, width)
    inner = width - 4
    label = (' ' + title + ' ')[:width - 2]
    top = '╭' + label + '─' * (width - 2 - len(label)) + '╮'
    return [top] + ['│ ' + row[:inner].ljust(inner) + ' │' for row in rows] + [
        '╰' + '─' * (width - 2) + '╯']
