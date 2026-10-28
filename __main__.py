#!/usr/bin/env python3
"""On-demand vLLM dashboard. Requires Python 3 and the ssh client locally."""

import argparse
import concurrent.futures
import contextlib
import curses
import getpass
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from collections import deque
from pathlib import Path
from litellm_usage import PERIODS, UsageClient, usage_table_rows
from credentials import key_path, load_api_key, save_api_key
from discovery import discover, endpoint_id, reconcile
from hosts import DEFAULT_PATTERN, discover_hosts
from settings import read_settings, settings_document
from updater import VERSION, notice, perform_update, should_recheck, version_badge
from banner import TITLE, title_banner
from preferences import MAX_DISPLAY_NAME, load_preferences, save_preferences
from themes import THEME_NAMES, apply_theme, normalize_theme


SAMPLE = re.compile(
    r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{.*\})?\s+'
    r'([-+]?(?:\d*\.?\d+(?:[eE][-+]?\d+)?|Inf|NaN))(?:\s|$)'
)

# A release published while the monitor is running must still show its badge.
UPDATE_CHECK_SECONDS = 300

# A short read-only probe, at most once per five seconds per host. No agent,
# service, package or file is installed on the machines.
HARDWARE_PROBE = r'''
import csv, json, subprocess
result = {}
try:
    p = subprocess.run(['nvidia-smi',
        '--query-gpu=index,temperature.gpu,utilization.gpu,power.draw,temperature.gpu.tlimit',
        '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3)
    if p.returncode == 0:
        result['gpus'] = [[v.strip() for v in row] for row in csv.reader(p.stdout.splitlines())]
    else:
        result['gpu_error'] = p.stderr.strip() or 'nvidia-smi failed'
except Exception as exc:
    result['gpu_error'] = str(exc)
try:
    with open('/proc/meminfo') as f:
        mem = {line.split(':')[0]: int(line.split()[1]) for line in f}
    result['ram_total'] = mem['MemTotal'] / 1048576
    result['ram_used'] = (mem['MemTotal'] - mem['MemAvailable']) / 1048576
    result['swap_used'] = (mem['SwapTotal'] - mem['SwapFree']) / 1048576
    with open('/proc/loadavg') as f:
        result['load'] = f.read().split()[0]
except Exception as exc:
    result['memory_error'] = str(exc)
print(json.dumps(result))
'''
MENU_WIDTH = 48
MENU_ITEMS = 2


def resolve_display_name(custom_name, key_alias):
    """Custom name wins, then the key alias, then the built-in title."""
    for value in (custom_name, key_alias):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return TITLE


def cycle_theme(current, step):
    """Move through the canonical theme list, wrapping in both directions."""
    theme = normalize_theme(current)
    index = THEME_NAMES.index(theme) + int(step)
    return THEME_NAMES[index % len(THEME_NAMES)]


def _menu_row(text):
    inner = MENU_WIDTH - 4
    return '│ ' + text[:inner].ljust(inner) + ' │'


def menu_lines(theme, display_name, selection, editing=False, input_text='', error=''):
    """Return the popup as fixed-width lines, including its border."""
    theme = normalize_theme(theme)
    selection = 1 if editing else (0 if selection == 0 else 1)
    marks = ['▶ ' if selection == 0 else '  ', '▶ ' if selection == 1 else '  ']
    label = ' НАСТРОЙКИ '
    lines = ['╭' + label + '─' * (MENU_WIDTH - 2 - len(label)) + '╮',
             _menu_row(marks[0] + 'Тема: ' + theme),
             _menu_row(marks[1] + 'Имя: ' + (input_text + '█' if editing
                                             else str(display_name)))]
    if error:
        lines.append(_menu_row('Ошибка: ' + str(error)))
    lines.append(_menu_row(''))
    if editing:
        lines.append(_menu_row('Enter — сохранить · Esc — отмена'))
        lines.append(_menu_row('Ctrl+U — очистить · пусто = имя ключа'))
    else:
        lines.append(_menu_row('↑↓ выбор · ←→ тема · Enter · m/Esc'))
    lines.append('╰' + '─' * (MENU_WIDTH - 2) + '╯')
    return lines


def menu_row_attr(row, line, count, color):
    """Pick the text color for a popup row; borders are handled separately."""
    if row in (0, count - 1):
        return color(9) | curses.A_BOLD
    if line.startswith('│ Ошибка:'):
        return color(4) | curses.A_BOLD
    if '▶' in line:
        return color(3) | curses.A_BOLD
    if row >= count - 2:
        return color(1)
    return color(7)


def draw_menu(screen, popup, popup_x, popup_y, terminal_width, terminal_height, color):
    """Draw the popup with a single border color from the active theme."""
    border_attr = color(9) | curses.A_BOLD
    for row, line in enumerate(popup):
        y = popup_y + row
        if y > terminal_height - 2:
            break
        attr = menu_row_attr(row, line, len(popup), color)
        try:
            screen.addnstr(y, popup_x, line,
                           max(1, terminal_width - popup_x - 1), attr)
            # The vertical edges must stay in the border color even though
            # the rest of the row uses the item's own color.
            if 0 < row < len(popup) - 1 and len(line) >= 2:
                screen.addnstr(y, popup_x, line[0], 1, border_attr)
                screen.addnstr(y, popup_x + len(line) - 1, line[-1],
                               1, border_attr)
        except curses.error:
            pass


def footer_rows(settings_view, usage_view):
    """Return the two footer rows; the active view is highlighted in the UI."""
    if settings_view:
        first = [
            ('[v] Модели  ', False),
            ('[l] LiteLLM  ', False),
            ('[s] Static  ', True),
        ]
    elif usage_view:
        first = [
            ('[v] Модели  ', False),
            ('[l] LiteLLM  ', True),
            ('[s] Static  ', False),
        ]
    else:
        first = [
            ('[v] Модели  ', True),
            ('[l] LiteLLM  ', False),
            ('[s] Static  ', False),
        ]
    second = []
    if not usage_view:
        second.append(('[tab] Смена  ', False))
    second.extend([
        ('[m] Меню  ', False),
        ('[h] Пояснения  ', False),
        ('[q] Выход', False),
    ])
    rows = (first, second)
    return tuple([[(text, active) for text, active in row] for row in rows])


def footer_line(settings_view, usage_view, row=0):
    return ''.join(text for text, _ in footer_rows(settings_view, usage_view)[row])


def tab_effect(settings_view, usage_view, settings_tab, embeddings):
    """Return (settings_tab, embeddings) after Tab; LiteLLM is inert."""
    if settings_view:
        return ('sparks' if settings_tab == 'providers' else 'providers'), embeddings
    if usage_view:
        return settings_tab, embeddings
    return settings_tab, not embeddings


def restart_requested(key, update_state):
    return key == 'r' and (update_state or {}).get('status') == 'updated'


def normalize_key(key):
    return {'Q': 'q', 'й': 'q', 'Й': 'q', 'H': 'h', 'р': 'h', 'Р': 'h',
            'L': 'l', 'д': 'l', 'Д': 'l', 'S': 's', 'ы': 's', 'Ы': 's',
            'M': 'm', 'm': 'm', 'ь': 'm', 'Ь': 'm',
            'V': 'v', 'v': 'v', 'м': 'v', 'М': 'v',
            'R': 'r', 'r': 'r', 'к': 'r', 'К': 'r', '−': '-'}.get(key, key)


def parse_metrics(text):
    values = {}
    for line in text.splitlines():
        match = SAMPLE.match(line)
        if match:
            value = float(match[2])
            if math.isfinite(value):
                values.setdefault(match[1], []).append(value)
                if match[1] == 'velogb10_requests_total' and re.search(
                        r'\bfinish="(?:stop|length|tool_calls)"', line):
                    values.setdefault('_monitor_qwen_success_total', []).append(value)
    return values


def format_metric(values, names, percent=False):
    for name in names:
        entries = values.get(name)
        if entries:
            if percent:
                lo, hi = min(entries) * 100, max(entries) * 100
                return f'{lo:.1f}%' if lo == hi else f'{lo:.1f}–{hi:.1f}%'
            return f'{sum(entries):g}'
    return 'нет данных'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def render(lines, interactive):
    if interactive:
        width, height = shutil.get_terminal_size()
        lines = [''.join(c for c in line if c.isprintable())[:max(1, width - 1)]
                 for line in lines[:max(1, height - 1)]]
        print('\033[H' + '\n'.join(lines) + '\033[J', end='', flush=True)
    else:
        print('\n'.join(lines), flush=True)


class History:
    """Counter deltas over up to 60 seconds, never lifetime averages."""

    def __init__(self):
        self.points = deque()

    def add(self, now, values):
        # A counter reset invalidates the observation window.
        if self.points:
            previous = self.points[-1][1]
            if any(sum(values[n]) < sum(previous[n]) for n in values
                   if n.endswith(('_total', '_sum', '_count')) and n in previous):
                self.points.clear()
        self.points.append((now, values))
        while len(self.points) > 1 and self.points[0][0] < now - 60:
            self.points.popleft()

    def delta(self, name):
        if len(self.points) < 2:
            return None
        old, new = self.points[0][1], self.points[-1][1]
        if name not in old or name not in new:
            return None
        value = sum(new[name]) - sum(old[name])
        return value if value >= 0 else None

    @property
    def span(self):
        return self.points[-1][0] - self.points[0][0] if len(self.points) > 1 else 0

    def rate(self, name):
        delta = self.delta(name)
        return delta / self.span if delta is not None and self.span > 0 else None

    def mean(self, name):
        total, count = self.delta(name + '_sum'), self.delta(name + '_count')
        return total / count if total is not None and count else None

    def ratio(self, numerator, denominator):
        num, den = self.delta(numerator), self.delta(denominator)
        return num / den if num is not None and den else None


def number(value, suffix='', scale=1):
    return '—' if value is None else f'{value * scale:.2f}{suffix}'


def change_interval(interval, key):
    if key == '-':
        return min(60000, interval + 250)
    if key in ('=', '+'):
        return max(250, interval - 250)
    return interval


def dashboard_rows(values, history, embedding=False):
    gauge = lambda name: format_metric(values, ['vllm:' + name])
    mean = lambda name: history.mean('vllm:' + name)
    rate = lambda name: history.rate('vllm:' + name)
    rows = [
        ('СЕЙЧАС', '', ''),
        ('Обрабатываются', gauge('num_requests_running'), 'Запросы в execution batches'),
        ('Очередь', gauge('num_requests_waiting'), 'Ждут планировщика vLLM'),
        ('KV-cache', format_metric(values, ['vllm:kv_cache_usage_perc',
                                         'vllm:gpu_cache_usage_perc'], percent=True),
         'При заполнении возможны вытеснения'),
        ('СКОРОСТЬ · ОКНО ДО 60 С', '', ''),
        ('Генерация', number(rate('generation_tokens_total'), ' tok/s'), 'Сумма по всем запросам, НЕ на клиента'),
        ('Входные токены', number(rate('prompt_tokens_total'), ' tok/s'), 'Темп обработки входа'),
        ('Завершено успешно', number(rate('request_success_total'), ' req/s'), 'Включает разные причины завершения'),
        ('Вытеснения', number(rate('num_preemptions_total'), ' /s'), 'Рост может указывать на давление KV-cache'),
        ('Prefix-cache hit', number(history.ratio('vllm:prefix_cache_hits_total',
                                                'vllm:prefix_cache_queries_total'), '%', 100),
         'Доля попаданий по токенам'),
        ('ЗАДЕРЖКИ · СРЕДНИЕ ПО НАБЛЮДЕНИЯМ В ОКНЕ', '', ''),
        ('Первый токен / TTFT', number(mean('time_to_first_token_seconds'), ' s'), 'Очередь + подготовка первого токена'),
        ('Между токенами / ITL', number(mean('inter_token_latency_seconds'), ' ms', 1000), 'Задержка выдачи следующих токенов'),
        ('Полный запрос / E2E', number(mean('e2e_request_latency_seconds'), ' s'), 'Только завершённые наблюдения'),
        ('Ожидание в очереди', number(mean('request_queue_time_seconds'), ' s'), 'Среднее, не возраст текущей очереди'),
        ('Prefill', number(mean('request_prefill_time_seconds'), ' s'), 'Подготовка входного контекста'),
        ('Decode', number(mean('request_decode_time_seconds'), ' s'), 'Генерация ответа'),
        ('ДЛИНЫ · СРЕДНИЕ ПО НАБЛЮДЕНИЯМ В ОКНЕ', '', ''),
        ('Вход', number(mean('request_prompt_tokens'), ' tok'), 'Длинный вход может увеличивать prefill'),
        ('Ответ', number(mean('request_generation_tokens'), ' tok'), 'Длинный ответ увеличивает полное время'),
    ]
    if embedding:
        excluded = {'Генерация', 'Первый токен / TTFT', 'Между токенами / ITL',
                    'Decode', 'Ответ'}
        rows = [row for row in rows if row[0] not in excluded]
        rows.insert(1, ('Режим', 'Embedding', 'Векторы, не генерация текста'))
        rows.insert(-2, ('Выполнение', number(mean('request_inference_time_seconds'), ' s'),
                         'Время выполнения embedding-запроса'))
    return rows


def read_metrics(http, url):
    with http.open(url, timeout=2) as response:
        values = parse_metrics(response.read(4000000).decode('utf-8', 'replace'))
    if not any(name.startswith(('vllm:', 'velogb10_')) for name in values):
        raise ValueError('Ответ не содержит метрик vLLM/gb10')
    return values


def generation_qwen_rows(values, history):
    gauge = lambda name: format_metric(values, ['velogb10_' + name])
    mean = lambda name: history.mean('velogb10_' + name)
    rate = lambda name: history.rate('velogb10_' + name)
    return [
        ('СЕЙЧАС', '', ''),
        ('Обрабатываются', gauge('requests_running'), 'Запросы, занимающие lane'),
        ('Очередь', gauge('requests_waiting'), 'Запросы, ожидающие lane'),
        ('Вместимость', gauge('max_batch'), 'Лимит одновременно занятых lanes'),
        ('Потоки процесса', gauge('thread_count'), 'OS-потоки сервера, не запросы'),
        ('СКОРОСТЬ · ОКНО ДО 60 С', '', ''),
        ('Генерация', number(rate('generation_tokens_total'), ' tok/s'),
         'Токены учитываются только при завершении запроса'),
        ('Входные токены', number(rate('prompt_tokens_total'), ' tok/s'),
         'Токены завершённых запросов, не мгновенный prefill'),
        ('Завершено успешно', number(history.rate('_monitor_qwen_success_total'), ' req/s'),
         'Завершения stop/length/tool_calls, без error/cancelled'),
        ('Отклонено', number(rate('requests_rejected_total'), ' req/s'), 'Отказы при переполнении очереди'),
        ('Prefix-cache hit', number(history.ratio('velogb10_prompt_tokens_cached_total',
                                                'velogb10_prompt_tokens_total'), '%', 100),
         'Кешированные входные токены завершённых запросов'),
        ('ЗАДЕРЖКИ · СРЕДНИЕ ПО НАБЛЮДЕНИЯМ В ОКНЕ', '', ''),
        ('Первый токен / TTFT', number(mean('time_to_first_token_seconds'), ' s'),
         'Включает очередь и prefill'),
        ('Полный запрос / E2E', number(mean('request_duration_seconds'), ' s'),
         'От получения запроса до конца ответа'),
        ('Скорость Decode', number(mean('decode_tokens_per_second'), ' tok/s'),
         'Средняя скорость после первого токена, не общая скорость'),
        ('Скорость Prefill', number(mean('prefill_tokens_per_second'), ' tok/s'),
         'Входные токены / TTFT; включает время очереди'),
    ]


def model_metric_rows(model):
    if model['kind'] == 'embedding':
        return dashboard_rows(model['values'], model['history'], True)
    rows = (generation_qwen_rows(model['values'], model['history']) if model['kind'] == 'gb10'
            else dashboard_rows(model['values'], model['history']))
    by_name = {row[0]: row for row in rows}
    # One shared schema keeps labels, units and row positions aligned. A missing
    # backend metric is unavailable, never fabricated from an unrelated metric.
    schema = dashboard_rows({}, History())
    order = [row[0] for row in schema]
    sections = {name for name, value, note in schema if not value and not note}
    notes = {name: note for name, _, note in schema}
    notes.update({
        'Обрабатываются': 'Запросы, которые сейчас обрабатывает модель',
        'Очередь': 'Запросы, ожидающие обработки сервером модели',
        'Вместимость': 'Максимум одновременно обрабатываемых последовательностей',
        'Потоки процесса': 'OS-потоки сервера, не число запросов',
        'Генерация': 'Суммарный темп выходных токенов, tok/s',
        'Входные токены': 'Суммарный темп входных токенов, tok/s',
        'Завершено успешно': 'Успешные завершения в секунду, без ошибок и отмен',
        'Отклонено': 'Запросы, отклонённые при приёме, в секунду',
        'Prefix-cache hit': 'Доля входных токенов, обслуженных prefix-кешем',
        'Первый токен / TTFT': 'От приёма запроса до первого токена, включая очередь',
        'Полный запрос / E2E': 'От приёма запроса до конца ответа',
        'Скорость Prefill': 'Средняя скорость обработки входа на запрос, tok/s',
        'Скорость Decode': 'Средняя скорость генерации на запрос, tok/s',
    })
    index = order.index('KV-cache')
    order[index:index] = ['Вместимость', 'Потоки процесса']
    index = order.index('Вытеснения')
    order[index:index] = ['Отклонено']
    index = order.index('ЗАДЕРЖКИ · СРЕДНИЕ ПО НАБЛЮДЕНИЯМ В ОКНЕ')
    order[index:index] = ['Скорость Prefill', 'Скорость Decode']
    fallback = {'Вместимость': model.get('capacity'), 'Потоки процесса': model.get('threads')}
    result = []
    for name in order:
        if name in sections:
            result.append((name, '', ''))
            continue
        value = by_name.get(name, (name, '—', ''))[1]
        # gb10 gauges report 'нет данных' when /metrics lacks the field, so both
        # that and the vLLM placeholder '—' are treatable as missing.
        if value in ('—', 'нет данных') and fallback.get(name) is not None:
            value = str(fallback[name])
        result.append((name, value, notes[name]))
    return result


def model_table_rows(model, show_help, now):
    age = f"{now - model['last']:.1f}s" if model['last'] is not None else '—'
    rows = [f"{model['status']} | возраст {age} | окно {model['history'].span:.0f}s",
            'МЕТРИКА                    │ ЗНАЧЕНИЕ' + ('         │ ПОЯСНЕНИЕ' if show_help else '')]
    for name, value, note in model_metric_rows(model):
        if not value and not note:
            rows.append('━ ' + name)
        else:
            rows.append(f'{name:26} │ {value:16}' + (' │ ' + note if show_help else ''))
    return rows


def selected_models(models, embeddings):
    return [model for model in models if (model['kind'] == 'embedding') == embeddings]


def model_tables(models, width, show_help, now):
    rows = [model_table_rows(model, show_help, now) for model in models]
    side_by_side = len(models) == 2 and width >= (160 if show_help else 112)
    if side_by_side:
        left_width = (width - 2) // 2
        widths = (left_width, width - 2 - left_width)
        row_count = max(map(len, rows))
        tables = [framed_table(model['name'], body + [''] * (row_count - len(body)), column_width)
                  for model, body, column_width in zip(models, rows, widths)]
        return [left + '  ' + right for left, right in zip(*tables)]
    lines = []
    for model, body in zip(models, rows):
        if lines:
            lines.append('')
        lines.extend(framed_table(model['name'], body, width))
    return lines


def read_hardware(host, user):
    try:
        proc = subprocess.run([
            'ssh', '-T', '-S', 'none', '-o', 'ControlMaster=no',
            '-o', 'ControlPersist=no', '-o', 'ForkAfterAuthentication=no',
            '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
            '-o', 'ServerAliveInterval=2', '-o', 'ServerAliveCountMax=1',
            '-l', user, host, 'python3 -',
        ], input=HARDWARE_PROBE, text=True, capture_output=True, timeout=7)
        if proc.returncode:
            return {'error': proc.stderr.strip() or f'SSH exit {proc.returncode}'}
        return json.loads(proc.stdout)
    except Exception as exc:
        return {'error': str(exc)}


def framed_table(title, rows, width):
    """Return a bounded table; caller may scroll the complete document."""
    width = max(4, width)
    inner = width - 4
    label = (' ' + title + ' ')[:width - 2]
    top = '╭' + label + '─' * (width - 2 - len(label)) + '╮'
    return [top] + ['│ ' + row[:inner].ljust(inner) + ' │' for row in rows] + [
        '╰' + '─' * (width - 2) + '╯']


def hardware_rows(hardware, hosts, now):
    rows = ['ХОСТ                              │ GPU °C │ GPU % │ W     │ RAM GiB       │ SWAP  │ LOAD1 │ ВОЗРАСТ']
    for host in hosts:
        entry = hardware.get(host['ip'])
        if not entry:
            rows.append(f'{host["name"]} · подключение…')
            continue
        timestamp, data = entry
        age = f'{now - timestamp:.0f}s'
        if 'error' in data:
            rows.append(f'{host["name"]} · НЕТ ДАННЫХ: {data["error"]}')
            continue
        memory = (f"{data['ram_used']:.1f}/{data['ram_total']:.1f}"
                  if 'ram_used' in data else '—')
        swap = f"{data['swap_used']:.1f}" if 'swap_used' in data else '—'
        gpus = [gpu for gpu in data.get('gpus', []) if len(gpu) >= 4]
        if gpus:
            for gpu in gpus:
                index, temp, util, power = gpu[:4]
                label = f'{host["name"]} GPU {index}'[:33].ljust(33)
                rows.append(f'{label} │ {temp:6} │ {util:5} │ {power:5} │ '
                            f'{memory:13} │ {swap:5} │ {data.get("load", "—"):5} │ {age}')
        else:
            rows.append(host['name'])
        if 'gpu_error' in data:
            rows.append(f'{host["name"]} · GPU: {data["gpu_error"]}')
        if 'memory_error' in data:
            rows.append(f'{host["name"]} · RAM: {data["memory_error"]}')
    return rows


def numeric(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def temperature_severity(gpu):
    # NVIDIA T.Limit is remaining thermal headroom, NOT an absolute temperature.
    # Prefer it over fixed thresholds when the driver exposes it.
    margin = numeric(gpu[4]) if len(gpu) >= 5 else None
    if margin is not None:
        return 'critical' if margin <= 0 else 'warning' if margin <= 5 else None
    temperature = numeric(gpu[1])
    if temperature is None:
        return None
    return 'critical' if temperature >= 90 else 'warning' if temperature >= 80 else None


def document_alerts(lines, hardware, hosts):
    """Color individual values, not entire tables. High utilization is normal."""
    by_name = {host['name']: host['ip'] for host in hosts}
    host = None
    alerts = []
    for line in lines:
        spans = []
        body = line[1:].strip() if line.startswith('│') else ''
        for name, address in by_name.items():
            if body == name or body.startswith(name + ' '):
                host = address
                break
        gpu_match = re.search(r'GPU (\d+)[^│]*│(\s*[^│]+)', line)
        data = hardware.get(host, (None, {}))[1]
        if gpu_match:
            gpu = next((gpu for gpu in data.get('gpus', [])
                        if gpu[0] == gpu_match[1]), None)
            if gpu:
                severity = temperature_severity(gpu)
                if severity:
                    spans.append((*gpu_match.span(2), severity))
            memory = re.search(r'│\s*(\d+\.\d+/\d+\.\d+)', line)
            if memory and 'ram_total' in data and 'ram_used' in data:
                free = data['ram_total'] - data['ram_used']
                severity = 'critical' if free < 1 else 'warning' if free < 4 else None
                if severity:
                    spans.append((*memory.span(1), severity))
        for match in re.finditer(r'KV-cache\s*│\s*(\d+(?:\.\d+)?%)', line):
            usage = float(match[1][:-1])
            severity = 'critical' if usage >= 99 else 'warning' if usage >= 95 else None
            if severity:
                spans.append((*match.span(1), severity))
        for match in re.finditer(r'Очередь\s*│\s*(\d+(?:\.\d+)?)', line):
            if float(match[1]) > 0:
                spans.append((*match.span(1), 'warning'))
        for match in re.finditer(r'Отклонено\s*│\s*(\d+(?:\.\d+)?\s*req/s)', line):
            if float(match[1].split()[0]) > 0:
                spans.append((*match.span(1), 'critical'))
        for match in re.finditer(r'НЕТ (?:СВЕЖИХ )?ДАННЫХ[^│]*|SSH: [^│]*', line):
            spans.append((*match.span(), 'critical'))
        alerts.append(spans)
    return alerts


def table_heading_spans(line):
    """Adjacent cards share a screen row, but never share row styling."""
    spans = []
    start = 0
    boundaries = list(re.finditer(r'(?<=[│╮╯])  (?=[│╭╰])', line))
    for end, next_start in [(match.start(), match.end()) for match in boundaries] + [(len(line), len(line))]:
        part = line[start:end]
        if part.startswith(('╭', '╰', '│ ━', '│ МЕТРИКА', '│ ХОСТ')):
            spans.append((start, end))
        start = next_start
    return spans


def table_rule_spans(line):
    return [(index, index + 1) for index, char in enumerate(line) if char == '│']


def run_dashboard(screen, args, models, hosts, http, usage):
    try:
        preferences = load_preferences()
    except (OSError, ValueError):
        preferences = {}
    theme = normalize_theme(preferences.get('theme'))
    custom_name = preferences.get('display_name', '')
    display_name = custom_name or TITLE
    if screen is not None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        screen.timeout(50)
        try:
            screen.keypad(True)
        except curses.error:
            pass
        if curses.has_colors():
            curses.start_color()
            apply_theme(theme)
    next_poll, offset = 0, 0
    hardware, probes = {}, {}
    next_hardware = 0
    embeddings, show_help = args.embeddings, args.explain
    usage_view, usage_period = args.usage and not args.settings, args.period
    settings_view = args.settings
    settings_tab = 'providers'
    usage_cache, usage_errors, usage_due = {}, {}, {}
    usage_pending = None
    settings_cache, settings_errors, settings_pending = {}, {}, {}
    next_settings = 0
    provider_cache, provider_error, provider_pending = None, '', None
    next_provider = 0
    discovery_pending, discovery_state = {}, {}
    next_discovery = 0
    discovery_hosts = tuple(host['ip'] for host in hosts)
    host_names = {host['ip']: host['name'] for host in hosts}
    update_pending = None
    update_state = {}
    next_update = 0
    key_alias, alias_pending = '', None
    menu_open, menu_selection, editing = False, 0, False
    menu_input, menu_error = '', ''
    deadline = time.monotonic() + 10
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool, contextlib.ExitStack() as shutdown:
        shutdown.callback(usage.close)
        if screen is not None:
            alias_pending = pool.submit(usage.key_alias)
        while True:
            now = time.monotonic()
            if alias_pending is not None and alias_pending.done():
                future, alias_pending = alias_pending, None
                try:
                    alias = future.result()
                except Exception:
                    alias = ''
                if isinstance(alias, str) and alias.strip():
                    key_alias = alias.strip()
                    if not custom_name:
                        display_name = key_alias
            if not args.no_discovery:
                for host in list(discovery_pending):
                    if discovery_pending[host].done():
                        snapshot = discovery_pending.pop(host).result()
                        discovery_state[host] = snapshot
                        reconcile(models, host, snapshot,
                                  lambda item: create_model(item, args.user, automatic=True,
                                                            host_label=host_names.get(item['host'])),
                                  close_model)
                if now >= next_discovery:
                    for host in discovery_hosts:
                        if host not in discovery_pending:
                            discovery_pending[host] = pool.submit(discover, host, args.user)
                    next_discovery = now + 30
            if usage_pending is not None and usage_pending[1].done():
                period, future = usage_pending
                try:
                    usage_cache[period] = (now, future.result())
                    usage_errors.pop(period, None)
                except Exception as exc:
                    usage_errors[period] = str(exc)
                usage_pending = None
            if usage_view and usage_pending is None and now >= usage_due.get(usage_period, 0):
                usage_pending = (usage_period, pool.submit(usage.fetch, usage_period))
                usage_due[usage_period] = now + 60
            for host in list(settings_pending):
                if settings_pending[host].done():
                    future = settings_pending.pop(host)
                    try:
                        snapshot = future.result()
                    except Exception as exc:
                        settings_errors[host] = f'опрос: {exc}'
                        continue
                    if snapshot.get('error'):
                        settings_errors[host] = snapshot['error']
                    else:
                        settings_cache[host] = (now, snapshot)
                        settings_errors.pop(host, None)
            if settings_view and settings_tab == 'sparks' and now >= next_settings:
                for host in hosts:
                    if host['ip'] not in settings_pending:
                        settings_pending[host['ip']] = pool.submit(read_settings, host['ip'], args.user)
                next_settings = now + 60
            if provider_pending is not None and provider_pending.done():
                future = provider_pending
                provider_pending = None
                try:
                    provider_cache = (now, future.result())
                    provider_error = ''
                except Exception as exc:
                    provider_error = str(exc)
            if (settings_view and settings_tab == 'providers' and provider_pending is None
                    and now >= next_provider):
                provider_pending = pool.submit(usage.model_info)
                next_provider = now + 60
            if update_pending is not None and update_pending.done():
                future = update_pending
                update_pending = None
                try:
                    update_state = future.result()
                except Exception as exc:
                    update_state = {'status': 'error', 'error': str(exc)}
                if should_recheck(update_state):
                    next_update = now + UPDATE_CHECK_SECONDS
            if (screen is not None and not args.no_update_check
                    and update_pending is None and should_recheck(update_state)
                    and now >= next_update):
                update_pending = pool.submit(perform_update, args.archive)
            for host in list(probes):
                if probes[host].done():
                    hardware[host] = (now, probes.pop(host).result())
            if now >= next_hardware:
                for host in hosts:
                    if host['ip'] not in probes:
                        probes[host['ip']] = pool.submit(read_hardware, host['ip'], args.user)
                next_hardware = now + max(5, args.interval / 1000)
            for model in models:
                pending = model['pending']
                if pending is not None and pending.done():
                    try:
                        model['values'] = pending.result()
                        model['history'].add(now, model['values'])
                        model.update(last=now, status='LIVE', ready=True)
                    except Exception as exc:
                        model['status'] = f'НЕТ СВЕЖИХ ДАННЫХ: {exc}'
                        model['ready'] = now >= deadline
                    model['pending'] = None
                if model['tunnel'].poll() is not None and not model.get('missing'):
                    model['errors'].seek(0)
                    model['status'] = 'SSH: ' + (model['errors'].read().strip() or 'туннель закрылся')
                    model['ready'] = True
            active = selected_models(models, embeddings)
            discovery_ready = args.no_discovery or len(discovery_state) == len(discovery_hosts)
            if args.once and discovery_ready and all(model['ready'] for model in active) and len(hardware) == len(hosts):
                lines = [f'{TITLE} | v{VERSION} | {datetime.now():%H:%M:%S}']
                lines.extend(framed_table('КАЖДЫЙ SPARK · GPU/RAM', hardware_rows(hardware, hosts, now), 110))
                lines.extend(discovery_rows(args, discovery_state, hosts))
                for model in active:
                    lines.extend(framed_table(model['name'], model_table_rows(model, show_help, now), 110))
                render(lines, False)
                return
            if now >= next_poll:
                for model in models:
                    if not model.get('missing') and model['pending'] is None and model['tunnel'].poll() is None:
                        model['pending'] = pool.submit(read_metrics, http, model['url'])
                next_poll = now + args.interval / 1000
            if screen is None:
                time.sleep(0.05)
                continue

            terminal_height, terminal_width = screen.getmaxyx()
            height, width = max(1, terminal_height - 2), max(1, terminal_width - 4)
            color = lambda pair: curses.color_pair(pair) if curses.has_colors() else 0

            def put(y, text, attr=0):
                if 0 <= y < height:
                    try:
                        screen.addnstr(y + 1, 2, ''.join(c for c in text if c.isprintable()),
                                       width, attr)
                    except curses.error:
                        pass

            screen.erase()
            try:
                screen.attron(color(9))
                screen.border()
                screen.attroff(color(9))
            except curses.error:
                pass
            banner = title_banner(display_name, width)
            for y, line in enumerate(banner):
                put(y, line, color((5, 6, 7, 8, 9, 10, 7, 7, 7)[y]) | curses.A_BOLD)
            header_height = len(banner)
            mode = ('STATIC · ПРОВАЙДЕРЫ' if settings_view and settings_tab == 'providers' else
                    'STATIC · SPARK' if settings_view else
                    'LITELLM · ' + PERIODS[usage_period][1] if usage_view else
                    'EMBEDDING' if embeddings else 'ОБЫЧНЫЕ МОДЕЛИ')
            badge = version_badge(update_state)
            version_prefix = f' {mode} | v{VERSION}'
            header = (version_prefix + ((' ' + badge) if badge else '') +
                      f' | {datetime.now():%H:%M:%S} | {args.interval}ms | [-/+] частота')
            put(header_height, header, color(7))
            if badge and len(version_prefix) < width:
                try:
                    screen.addnstr(header_height + 1, 2 + len(version_prefix),
                                   ' ' + badge, width - len(version_prefix),
                                   color(3) | curses.A_BOLD)
                except curses.error:
                    pass
            update_notice = notice(update_state)
            if update_notice:
                if update_state.get('status') == 'updated':
                    update_notice = (f"Обновлено до {update_state.get('version')} · "
                                     '[r] перезапустить')
                header_height += 1
                put(header_height, ' ' + update_notice, color(3) | curses.A_BOLD)
            table_width = width
            hardware_table = framed_table('КАЖДЫЙ SPARK · GPU/RAM · опрос не чаще 5s',
                                          hardware_rows(hardware, hosts, now), table_width)
            if settings_view and settings_tab == 'providers':
                provider_data = provider_cache[1] if provider_cache else None
                document = settings_document(hosts, settings_cache, settings_errors, width, now,
                                             providers=provider_data,
                                             provider_error=provider_error,
                                             include_provider=True,
                                             include_sparks=False)
            elif settings_view:
                document = settings_document(hosts, settings_cache, settings_errors, width, now,
                                             include_sparks=True)
            elif usage_view:
                cached = usage_cache.get(usage_period)
                error = usage_errors.get(usage_period)
                body = ['[1] 1 день   [2] 7 дней   [3] 30 дней   [4] год · UTC · обновление 60s']
                title = 'LITELLM · KEY ACTIVITY'
                if error:
                    body.append('НЕТ СВЕЖИХ ДАННЫХ: ' + error)
                if cached:
                    timestamp, data = cached
                    title += f" · {data['start']} — {data['end']} UTC"
                    body.append(f'Возраст снимка {now - timestamp:.0f}s' + (' · УСТАРЕЛ' if error else ''))
                    body.extend(usage_table_rows(data))
                elif not error:
                    body.append('Загрузка статистики…')
                if show_help:
                    body.extend(['', 'Avg response = сумма времени / число запросов с измеренным временем.',
                                 'Дневные корзины LiteLLM, не скользящие 24 часа. История зависит от хранения сервера.',
                                 'Администратор: без key-hash. Личный режим: только текущий ключ, без вывода хеша.'])
                document = framed_table(title, body, width)
            else:
                document = hardware_table + discovery_rows(args, discovery_state, hosts) + [''] + model_tables(active, width, show_help, now)
                if not active:
                    document += ['Модели пока не обнаружены.' if not embeddings else 'Embedding-модели пока не обнаружены.']
            alerts = document_alerts(document, hardware, hosts)
            footer_height = 5 if show_help else 2
            visible = max(1, height - header_height - footer_height - 1)
            offset = min(offset, max(0, len(document) - visible))
            for index, line in enumerate(document[offset:offset + visible], offset):
                y = header_height + 1 + index - offset
                put(y, line)
                for start, end in table_heading_spans(line) + table_rule_spans(line):
                    if start >= width:
                        continue
                    try:
                        screen.addnstr(y + 1, start + 2, line[start:end], min(end, width) - start,
                                       color(7))
                    except curses.error:
                        pass
                for start, end, severity in alerts[index]:
                    if start >= width:
                        continue
                    try:
                        screen.addnstr(y + 1, start + 2, line[start:end], min(end, width) - start,
                                       color(4 if severity == 'critical' else 3) | curses.A_BOLD)
                    except curses.error:
                        pass
            if show_help:
                if settings_view:
                    put(height - 5, ' [Tab] — вкладка провайдеры/Spark; [m] — меню темы и имени; '
                                    '[s] — закрыть Static; секреты скрыты.')
                else:
                    put(height - 5, ' Автопоиск vLLM/gb10 каждые 30s. [m] — меню темы и имени; '
                                    '[s] — Static (статические настройки); секреты скрыты.')
                put(height - 4, ' GPU: T.Limit ≤5°C жёлтый, ≤0°C красный; без T.Limit: 80/90°C. RAM свободно <4/<1GiB; KV ≥95/99%.')
                put(height - 3, ' — = нет наблюдений. Средние до 60s, не p95. Qwen gb10: токены/s по завершениям. При ошибке данные УСТАРЕЛИ.')
            for footer_row, segments in zip((height - 1, height),
                                            footer_rows(settings_view, usage_view)):
                footer_x = 2
                for text, active in segments:
                    if footer_x >= terminal_width - 1:
                        break
                    # Pair 7 is the theme accent (header/headings); reverse
                    # turns it into a readable block for the active view.
                    attr = (color(7) | curses.A_BOLD | curses.A_REVERSE
                            if active else color(1))
                    try:
                        screen.addnstr(footer_row, footer_x, text,
                                       terminal_width - footer_x - 1, attr)
                    except curses.error:
                        pass
                    footer_x += len(text)
            if menu_open:
                popup = menu_lines(theme, display_name, menu_selection,
                                   editing, menu_input, menu_error)
                popup_x = max(2, min((terminal_width - MENU_WIDTH) // 2, terminal_width - 3))
                popup_y = max(1, min((terminal_height - len(popup)) // 2, terminal_height - 2))
                draw_menu(screen, popup, popup_x, popup_y, terminal_width,
                          terminal_height, color)
            screen.refresh()
            try:
                raw_key = screen.get_wch()
            except curses.error:
                continue
            key = normalize_key(raw_key)
            if menu_open:
                if editing:
                    # Name editing must preserve typed case and characters;
                    # normalize_key is only for dashboard commands.
                    if raw_key in ('\x1b', 27):
                        editing, menu_input, menu_error = False, '', ''
                    elif raw_key in ('\n', '\r', curses.KEY_ENTER):
                        custom_name = menu_input.strip()
                        display_name = resolve_display_name(custom_name, key_alias)
                        try:
                            save_preferences({'theme': theme, 'display_name': custom_name})
                            menu_error = ''
                        except (OSError, ValueError) as exc:
                            menu_error = str(exc)
                        editing, menu_input = False, ''
                    elif raw_key == '\x15':
                        menu_input = ''
                    elif raw_key in ('\x7f', '\b', curses.KEY_BACKSPACE):
                        menu_input = menu_input[:-1]
                    elif isinstance(raw_key, str) and len(raw_key) == 1 and raw_key.isprintable():
                        if len(menu_input) < MAX_DISPLAY_NAME:
                            menu_input += raw_key
                else:
                    if key in ('m', '\x1b', 27):
                        menu_open, menu_error = False, ''
                    elif key == curses.KEY_UP:
                        menu_selection = (menu_selection - 1) % MENU_ITEMS
                    elif key == curses.KEY_DOWN:
                        menu_selection = (menu_selection + 1) % MENU_ITEMS
                    elif key in (curses.KEY_LEFT, curses.KEY_RIGHT):
                        step = -1 if key == curses.KEY_LEFT else 1
                        theme = cycle_theme(theme, step)
                        apply_theme(theme)
                        try:
                            save_preferences({'theme': theme, 'display_name': custom_name})
                            menu_error = ''
                        except (OSError, ValueError) as exc:
                            menu_error = str(exc)
                    elif key in ('\n', '\r', curses.KEY_ENTER):
                        if menu_selection == 0:
                            theme = cycle_theme(theme, 1)
                            apply_theme(theme)
                            try:
                                save_preferences({'theme': theme, 'display_name': custom_name})
                                menu_error = ''
                            except (OSError, ValueError) as exc:
                                menu_error = str(exc)
                        else:
                            editing, menu_input, menu_error = True, custom_name, ''
                continue
            if key == 'm':
                menu_open, menu_selection, editing = True, 0, False
                menu_input, menu_error = '', ''
                continue
            if restart_requested(key, update_state):
                return 'restart'
            if key == 'v':
                usage_view = settings_view = False
                embeddings, offset = False, 0
                continue
            if key == 'q':
                return
            if key == '\t':
                if usage_view:
                    continue
                settings_tab, embeddings = tab_effect(
                    settings_view, usage_view, settings_tab, embeddings)
                offset = 0
                if settings_view:
                    if settings_tab == 'providers':
                        next_provider = 0
                    else:
                        next_settings = 0
            elif key == 'l':
                usage_view, offset = not usage_view, 0
                settings_view = False
            elif key == 's':
                settings_view, offset = not settings_view, 0
                usage_view = False
                next_settings = 0
                next_provider = 0
                if settings_view:
                    settings_tab = 'providers'
            elif usage_view and key in PERIODS:
                usage_period, offset = key, 0
            elif key == 'h':
                show_help = not show_help
            elif key in ('-', '=', '+'):
                args.interval = change_interval(args.interval, key)
                next_poll = time.monotonic() + args.interval / 1000
            elif key == curses.KEY_DOWN:
                offset += 1
            elif key == curses.KEY_UP:
                offset = max(0, offset - 1)
            elif key == curses.KEY_NPAGE:
                offset += visible
            elif key == curses.KEY_PPAGE:
                offset = max(0, offset - visible)


def discovery_rows(args, state, hosts):
    if args.no_discovery:
        return ['Ручные подключения · автопоиск выключен']
    rows = ['Автопоиск vLLM/gb10 · каждые 30s']
    for host in hosts:
        data = state.get(host['ip'])
        if data is None:
            rows.append(host['name'] + ': поиск…')
        elif data.get('error'):
            rows.append(host['name'] + ': НЕТ СВЕЖИХ ДАННЫХ: автопоиск недоступен')
        elif not data.get('docker_ok') or data.get('limited'):
            rows.append(host['name'] + ': неполный поиск (Docker недоступен или лимит портов)')
    return rows


def close_model(model):
    child = model['tunnel']
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    model['errors'].close()


def create_model(descriptor, user, automatic=False, host_label=None):
    local_port = free_port()
    errors = tempfile.TemporaryFile(mode='w+t')
    try:
        tunnel = start_tunnel(descriptor['host'], user, local_port,
                              descriptor['port'], errors, descriptor.get('address', '127.0.0.1'))
    except Exception:
        errors.close()
        raise
    return {'name': descriptor['name'] + ' · ' + (host_label or descriptor['host']) + ':' + str(descriptor['port']),
            'kind': descriptor['kind'], 'host': descriptor['host'],
            'automatic': automatic, 'endpoint': endpoint_id(descriptor),
            'identity': (descriptor['name'], descriptor['kind']),
            'capacity': descriptor.get('capacity'), 'threads': descriptor.get('threads'),
            'tunnel': tunnel, 'errors': errors,
            'url': f'http://127.0.0.1:{local_port}/metrics',
            'history': History(), 'values': {}, 'pending': None,
            'last': None, 'status': 'Подключение…', 'ready': False}


def start_tunnel(host, user, local_port, remote_port, errors, remote_address='127.0.0.1'):
    return subprocess.Popen([
        'ssh', '-N', '-T', '-S', 'none',
        '-o', 'ControlMaster=no', '-o', 'ControlPersist=no',
        '-o', 'ForkAfterAuthentication=no', '-o', 'BatchMode=yes',
        '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=5',
        '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=2',
        '-L', f'127.0.0.1:{local_port}:{remote_address}:{remote_port}',
        '-l', user, host,
    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors)


def find_litellm(hosts, override=None, timeout=2):
    """Use an explicit URL, otherwise find the LiteLLM health endpoint on Spark."""
    if override:
        return override.rstrip('/')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for host in hosts:
        url = f"http://{host['ip']}:4000"
        try:
            with opener.open(url + '/health/readiness', timeout=timeout) as response:
                if response.status == 200:
                    return url
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return None


def archive_path():
    candidate = Path(sys.argv[0])
    if candidate.suffix == '.pyz' and candidate.is_file():
        return candidate.resolve()
    return None


def manual_hosts(args):
    if not args.host:
        raise ValueError('Для --no-discovery нужен --host с адресом сервера')
    endpoints = [('VLLM', 'vllm', args.host, args.remote_port)]
    if args.qwen_host:
        endpoints.append(('QWEN', 'gb10', args.qwen_host, args.qwen_port))
    if args.embedding_host:
        endpoints.append(('EMBEDDING', 'embedding', args.embedding_host, args.embedding_port))
    hosts = [{'name': address, 'ip': address}
             for address in dict.fromkeys(item[2] for item in endpoints)]
    return endpoints, hosts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', help='manual server address; requires --no-discovery')
    parser.add_argument('--user', default='nvidia', help='SSH username')
    parser.add_argument('--remote-port', type=int, default=8000)
    parser.add_argument('--qwen-host', help='manual Qwen server address')
    parser.add_argument('--qwen-port', type=int, default=9001)
    parser.add_argument('--embedding-host', help='manual embedding server address')
    parser.add_argument('--embedding-port', type=int, default=8001)
    parser.add_argument('--spark-pattern', default=DEFAULT_PATTERN,
                        help='regex for Spark host names in Tailscale')
    parser.add_argument('--embeddings', action='store_true', help='start in embedding view')
    parser.add_argument('--explain', action='store_true', help='start with metric explanations')
    parser.add_argument('--usage', action='store_true', help='start in LiteLLM key activity view')
    parser.add_argument('--settings', action='store_true',
                        help='start in Static view on the providers tab')
    parser.add_argument('--period', choices=tuple(PERIODS), default='2', help='1=day, 2=week, 3=month, 4=year')
    parser.add_argument('--litellm-url', help='override the auto-detected LiteLLM address')
    parser.add_argument('--save-key', action='store_true', help='save LiteLLM key using hidden input, then exit')
    parser.add_argument('--interval', type=int, default=1000, help='milliseconds')
    parser.add_argument('--once', action='store_true', help='print one snapshot and exit')
    parser.add_argument('--no-discovery', action='store_true', help='use only manually configured endpoints')
    parser.add_argument('--no-update-check', action='store_true', help='do not contact GitHub Releases')
    parser.add_argument('--check-update', action='store_true', help='check for updates, then exit')
    parser.add_argument('--version', action='store_true', help='print version')
    args = parser.parse_args()
    if args.version:
        print(VERSION)
        return 0
    if args.save_key:
        if not sys.stdin.isatty():
            print('Для скрытого ввода ключа запустите --save-key в терминале.', file=sys.stderr)
            return 1
        try:
            save_api_key(getpass.getpass('LiteLLM API key (скрытый ввод): '))
        except (OSError, ValueError, EOFError) as exc:
            print(f'Не удалось сохранить ключ: {exc}', file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print('\nОтменено.', file=sys.stderr)
            return 130
        print(f'Ключ сохранён: {key_path()} (права 600).')
        return 0
    if not 250 <= args.interval <= 60000:
        parser.error('--interval must be between 250 and 60000 ms')
    if not shutil.which('ssh'):
        parser.error('ssh client not found')
    archive = archive_path()
    args.archive = archive
    if args.check_update:
        state = perform_update(archive)
        messages = {
            'current': f'Установлена последняя версия {VERSION}.',
            'updated': f"Обновлено до {state.get('version')}. Перезапустите монитор.",
            'available': f"Доступна версия {state.get('version')}, но обновление не установлено.",
            'unavailable': 'Автообновление доступно только при запуске файла .pyz.',
            'error': 'Проверка обновлений недоступна: ' + state.get('error', 'ошибка'),
        }
        print(messages.get(state['status'], 'Проверка обновлений завершена.'))
        return 0 if state['status'] in ('current', 'updated') else 1
    if not sys.stdout.isatty() and not args.once:
        parser.error('для TUI нужен терминал; для одного снимка используйте --once')

    try:
        api_key = load_api_key()
    except (OSError, ValueError) as exc:
        print(f'Ошибка чтения ключа: {exc}', file=sys.stderr)
        return 1
    try:
        endpoints, hosts = manual_hosts(args) if args.no_discovery else ([], None)
        if hosts is None:
            hosts, error = discover_hosts(args.spark_pattern)
            if error:
                print(f'Ошибка: {error}', file=sys.stderr)
                return 1
    except ValueError as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        return 1
    if args.once and args.settings:
        cache, errors = {}, {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(hosts))) as pool:
            futures = {host['ip']: pool.submit(read_settings, host['ip'], args.user) for host in hosts}
            for ip, future in futures.items():
                snapshot = future.result()
                if snapshot.get('error'):
                    errors[ip] = snapshot['error']
                else:
                    cache[ip] = (0, snapshot)
        providers, provider_error = None, ''
        litellm_url = find_litellm(hosts, args.litellm_url)
        if litellm_url:
            client = UsageClient(litellm_url, api_key)
            try:
                providers = client.model_info()
            except Exception as exc:
                provider_error = str(exc)
            finally:
                client.close()
        else:
            provider_error = 'LiteLLM не найден в tailnet'
        # Non-interactive snapshot has no tabs: print both sections.
        render(settings_document(hosts, cache, errors, 110, 0,
                                 providers=providers, provider_error=provider_error,
                                 include_provider=True, include_sparks=True), False)
        return 0
    litellm_url = find_litellm(hosts, args.litellm_url) if (args.usage or sys.stdout.isatty()) else None
    if args.once and args.usage and not litellm_url:
        print('Ошибка: LiteLLM не найден в tailnet. Укажите --litellm-url.', file=sys.stderr)
        return 1
    usage = UsageClient(litellm_url or '', api_key)
    if args.once and args.usage:
        try:
            data = usage.fetch(args.period)
            render(framed_table(f"LITELLM · {data['start']} — {data['end']} UTC", usage_table_rows(data), 110), False)
            return 0
        except Exception as exc:
            print(f'Ошибка: {exc}', file=sys.stderr)
            return 1
        finally:
            usage.close()

    interactive = sys.stdout.isatty() and not args.once
    # Ignore HTTP proxy environment variables for the local tunnel endpoint.
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    models = []
    exit_code = 0
    restart = False
    with contextlib.ExitStack() as stack:
        try:
            # A dedicated foreground SSH child: no -f, persistent master,
            # service, remote command, or remote file modifications.
            if args.no_discovery:
                for name, kind, host, remote_port in endpoints:
                    models.append(create_model({'name': name, 'kind': kind, 'host': host,
                                                'address': '127.0.0.1', 'port': remote_port}, args.user))
            if interactive:
                restart = curses.wrapper(run_dashboard, args, models, hosts, http,
                                         usage) == 'restart'
            else:
                run_dashboard(None, args, models, hosts, http, usage)
        except KeyboardInterrupt:
            pass
        except (OSError, RuntimeError) as exc:
            print(f'Ошибка: {exc}', file=sys.stderr)
            exit_code = 1
        finally:
            usage.close()
            for model in models:
                close_model(model)
    if restart:
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except OSError as exc:
            print(f'Ошибка перезапуска: {exc}', file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
