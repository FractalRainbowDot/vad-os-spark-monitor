"""Read-only LiteLLM daily analytics. Never displays credentials or key hashes."""

import ast
import hashlib
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


PERIODS = {'1': (1, '1 день'), '2': (7, '7 дней'),
           '3': (30, '30 дней'), '4': (365, 'год')}


def date_range(period, now=None):
    today = (now or datetime.now(timezone.utc)).date()
    return (today - timedelta(days=PERIODS[period][0] - 1)).isoformat(), today.isoformat()


def named_key(alias):
    return bool(alias and not re.match(r'^key[\s_-]*hash', alias.strip(), re.I))


def aggregate_usage(payload, catalog=(), personal_key=None):
    if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
        raise ValueError('LiteLLM: неизвестный формат статистики')
    groups = {}

    def record(identifier, metadata):
        alias = metadata.get('key_alias')
        if not named_key(alias):
            return None
        if identifier not in groups:
            groups[identifier] = dict(alias=alias, user=metadata.get('user_email') or
                                      metadata.get('user_id') or 'без пользователя',
                                      tokens=0, success=0, failed=0, duration_ms=0, timed=0)
        elif metadata.get('user_email'):
            groups[identifier]['user'] = metadata['user_email']
        return groups[identifier]

    lookup = {}
    for key in catalog:
        identifier = key.get('token') or key.get('api_key')
        if personal_key is not None and identifier != personal_key:
            continue
        if identifier:
            lookup[identifier] = key
            record(identifier, key)
    for day in payload['results']:
        breakdown = day.get('breakdown') or {}
        keys = breakdown.get('api_keys') or {}
        if not keys and (day.get('metrics') or {}).get('api_requests', 0):
            raise ValueError('LiteLLM не вернул разбивку по ключам; неполные итоги не показаны')
        for identifier, item in keys.items():
            if personal_key is not None and identifier != personal_key:
                continue
            metadata = dict(lookup.get(identifier, {}))
            metadata.update({k: v for k, v in (item.get('metadata') or {}).items() if v is not None})
            if personal_key is not None and not named_key(metadata.get('key_alias')):
                metadata['key_alias'] = 'Мой ключ'
            row = record(identifier, metadata)
            if row is None:
                continue
            metrics = item.get('metrics') or {}
            for source, target in (('total_tokens', 'tokens'), ('successful_requests', 'success'),
                                   ('failed_requests', 'failed'), ('total_response_time_ms', 'duration_ms'),
                                   ('timed_requests', 'timed')):
                row[target] += metrics.get(source) or 0
    return sorted(groups.values(), key=lambda row: (row['user'].casefold(), row['alias'].casefold()))


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward an Authorization header to another endpoint.


class APIError(RuntimeError):
    def __init__(self, status, llm_only=False):
        self.status = status
        self.llm_only = llm_only
        if status == 403 and llm_only:
            message = ('ключ разрешает только вызовы моделей (llm_api_routes). '
                       'Администратор должен разрешить чтение собственной статистики')
        else:
            message = {401: 'ключ недействителен', 403: 'ключу запрещён этот API статистики',
                       404: 'API статистики не найден'}.get(status, 'ошибка API')
        super().__init__(f'LiteLLM HTTP {status}: {message}')


class UsageClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip('/')
        self._api_key = api_key
        self._http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())
        self._catalog = None
        self._personal_key = None
        self._user_id = None
        self._scope = None
        self._stop = threading.Event()

    def close(self):
        self._stop.set()

    def get(self, path, **params):
        if self._stop.is_set():
            raise RuntimeError('Опрос остановлен')
        if not self._api_key:
            raise RuntimeError('Ключ не задан. Сохраните его: spark-monitor --save-key')
        if not self.base_url:
            raise RuntimeError('LiteLLM не найден в tailnet. Укажите --litellm-url.')
        url = self.base_url + path + '?' + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + self._api_key})
        try:
            with self._http.open(request, timeout=8) as response:
                raw = response.read(32000001)
                if len(raw) > 32000000:
                    raise ValueError('LiteLLM: ответ слишком большой')
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            # Inspect only to classify route restrictions. Never echo server
            # bodies: those can contain credentials or internal identifiers.
            body = exc.read(16000).decode('utf-8', 'replace')
            llm_only = False
            try:
                detail = json.loads(body).get('detail', '')
                match = re.search(r'Only allowed to call routes:\s*(\[[^\]]*\])', detail)
                if match:
                    routes = ast.literal_eval(match[1])
                    llm_only = isinstance(routes, list) and set(routes) == {'llm_api_routes'}
            except (ValueError, TypeError, SyntaxError, AttributeError):
                pass
            raise APIError(exc.code, llm_only) from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError('LiteLLM: нет соединения или истекло время ожидания') from None

    def catalog(self):
        if self._catalog is not None:
            return self._catalog
        try:
            identity = self.get('/user/info')
        except APIError as exc:
            if exc.llm_only or exc.status not in (403, 404):
                raise
            identity = {}
        user = identity.get('user_info') or {}
        # In this installed LiteLLM version, a successful user/info with null
        # user_info is only returned by the proxy-admin branch (e.g. master key).
        admin = (('user_info' in identity and identity['user_info'] is None) or
                 user.get('user_role') in ('proxy_admin', 'proxy_admin_viewer'))
        if not admin:
            self._personal_key = hashlib.sha256(self._api_key.encode()).hexdigest()
            self._user_id = identity.get('user_id') or user.get('user_id')
            self._scope = 'Только текущий ключ'
            candidates = identity.get('keys') or []
            metadata = next((key for key in candidates if isinstance(key, dict) and
                             (key.get('token') or key.get('api_key')) in (self._personal_key, self._api_key)), None)
            if metadata is None:
                try:
                    info = self.get('/key/info', key=self._personal_key)
                    metadata = info.get('info') or {}
                except APIError as exc:
                    if exc.llm_only or exc.status not in (403, 404):
                        raise
                    metadata = {}
            # This is the sole identity used by both the API filter and the
            # local filter. Never trust unrelated key rows in an API response.
            own = {'token': self._personal_key, 'user_id': self._user_id or 'Мой пользователь',
                   'key_alias': metadata.get('key_alias') if named_key(metadata.get('key_alias')) else 'Мой ключ'}
            self._catalog = [own]
            return self._catalog
        self._personal_key, self._user_id = None, None
        self._scope = 'Все пользователи · администратор'
        # The installed proxy's admin /user/info response already contains
        # every current key. Do not require an additional /key/list permission.
        keys = identity.get('keys')
        if not isinstance(keys, list) or any(not isinstance(key, dict) for key in keys):
            raise ValueError('LiteLLM: /user/info не вернул метаданные ключей')
        self._catalog = keys
        return keys

    def fetch(self, period):
        self._catalog = None  # Refresh aliases and include newly created idle keys.
        catalog = self.catalog()
        start, end = date_range(period)
        params = dict(start_date=start, end_date=end, timezone=0, include_current_utc_day='true')
        if self._personal_key is not None:
            params['api_key'] = self._personal_key
            if self._user_id:
                params['user_id'] = self._user_id
        payload = self.get('/user/daily/activity/aggregated', **params)
        if (payload.get('metadata') or {}).get('has_more'):
            raise ValueError('LiteLLM вернул неполную статистику')
        return {'rows': aggregate_usage(payload, catalog, self._personal_key),
                'start': start, 'end': end, 'scope': self._scope}


def usage_table_rows(data):
    rows = ['Доступ: ' + data.get('scope', 'Согласно правам ключа'),
            'ПОЛЬЗОВАТЕЛЬ / КЛЮЧ               │ TOTAL TOKENS    │ SUCCESSFUL │ FAILED   │ AVG RESPONSE']
    previous_user = None
    total = dict(tokens=0, success=0, failed=0, duration_ms=0, timed=0)
    for row in data.get('rows', []):
        if row['user'] != previous_user:
            rows.append(row['user'])
            previous_user = row['user']
        avg = f"{row['duration_ms'] / row['timed'] / 1000:.2f}s" if row['timed'] else '—'
        rows.append(f"  {row['alias'][:31]:31} │ {row['tokens']:15,d} │ {row['success']:10,d} │ "
                    f"{row['failed']:8,d} │ {avg}")
        for key in total:
            total[key] += row[key]
    avg = f"{total['duration_ms'] / total['timed'] / 1000:.2f}s" if total['timed'] else '—'
    label = 'ИТОГО · мой ключ' if data.get('scope') == 'Только текущий ключ' else 'ИТОГО (без key-hash)'
    rows.append(f"{label:33} │ {total['tokens']:15,d} │ {total['success']:10,d} │ "
                f"{total['failed']:8,d} │ {avg}")
    return rows
