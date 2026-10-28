import contextlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from discovery import PROBE, discover, endpoint_id, reconcile


spec = importlib.util.spec_from_file_location('monitor', Path(__file__).with_name('__main__.py'))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def descriptor(name='new-model', port=8123, kind='vllm'):
    return dict(name=name, port=port, kind=kind, host='192.0.2.10', address='127.0.0.1')


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.created, self.closed = [], []
        self.models = []

    def create(self, item):
        model = dict(item, automatic=True, endpoint=endpoint_id(item),
                     identity=(item['name'], item['kind']),
                     tunnel=SimpleNamespace(poll=lambda: None), values={}, pending=None)
        self.created.append(model)
        return model

    def apply(self, items, **extra):
        reconcile(self.models, '192.0.2.10', dict(models=items, **extra),
                  self.create, self.closed.append)

    def test_added_and_unchanged_preserves_history(self):
        self.apply([descriptor()])
        model = self.models[0]
        model['history'] = object()
        self.apply([descriptor()])
        self.assertIs(self.models[0], model)
        self.assertEqual(len(self.created), 1)

    def test_process_metadata_refreshes_without_replacing_tunnel(self):
        self.apply([dict(descriptor(), capacity=8, threads=60)])
        model = self.models[0]
        self.apply([dict(descriptor(), capacity=8, threads=61)])
        self.assertIs(self.models[0], model)
        self.assertEqual(model['capacity'], 8)
        self.assertEqual(model['threads'], 61)
        self.assertEqual(len(self.created), 1)

    def test_probe_miss_keeps_last_process_metadata(self):
        self.apply([dict(descriptor(), capacity=8, threads=60)])
        model = self.models[0]
        self.apply([descriptor()])
        self.assertIs(self.models[0], model)
        self.assertEqual(self.models[0]['capacity'], 8)
        self.assertEqual(self.models[0]['threads'], 60)

    def test_create_failure_keeps_old_model_and_retries_later(self):
        self.apply([descriptor('old')])
        model = self.models[0]
        model['values'] = {'old-metric': 123}

        def failing(item):
            if item['name'] == 'replacement':
                raise RuntimeError('ssh unavailable')
            return self.create(item)

        reconcile(self.models, '192.0.2.10', dict(models=[descriptor('replacement')]),
                  failing, self.closed.append)
        self.assertIs(self.models[0], model)
        self.assertEqual(model['name'], 'old')
        self.assertEqual(model['values'], {'old-metric': 123})
        self.assertEqual(self.closed, [])
        self.assertIn('НЕТ СВЕЖИХ', model['status'])
        self.assertTrue(model['ready'])

        self.apply([descriptor('replacement')])
        self.assertEqual(self.models[0]['name'], 'replacement')
        self.assertEqual(len(self.closed), 1)

    def test_replacement_on_same_port_resets_state(self):
        self.apply([descriptor('old')])
        self.models[0]['values'] = {'old-metric': 123}
        self.apply([descriptor('replacement', kind='embedding')])
        self.assertEqual(self.models[0]['name'], 'replacement')
        self.assertEqual(self.models[0]['values'], {})
        self.assertEqual(len(self.closed), 1)

    def test_stopped_then_reappearing(self):
        self.apply([descriptor()])
        self.models[0]['pending'] = object()
        self.apply([])
        self.assertTrue(self.models[0]['missing'])
        self.assertIsNone(self.models[0]['pending'])
        self.assertIn('НЕТ СВЕЖИХ', self.models[0]['status'])
        self.apply([descriptor()])
        self.assertFalse(self.models[0].get('missing', False))
        self.assertEqual(len(self.models), 1)

    def test_failed_discovery_never_erases_cards(self):
        self.apply([descriptor()])
        self.apply([], error='SSH unavailable')
        self.assertFalse(self.models[0].get('missing', False))
        self.assertEqual(len(self.closed), 0)

    def test_multiple_replicas_and_host_isolation(self):
        self.apply([descriptor(port=8123), descriptor(port=8124)])
        other = self.create(dict(descriptor(), host='192.0.2.11'))
        self.models.append(other)
        self.apply([])
        self.assertEqual(len(self.closed), 2)
        self.assertNotIn(other, self.closed)

    def test_dead_tunnel_is_recreated(self):
        self.apply([descriptor()])
        self.models[0]['tunnel'].poll = lambda: 255
        self.apply([descriptor()])
        self.assertEqual(len(self.created), 2)

    def test_remote_probe_finds_custom_port_and_embedding(self):
        requested = []
        def run(args, **kwargs):
            if args[0] == 'ss':
                text = ('LISTEN 0 128 0.0.0.0:8123 0.0.0.0:*\n'
                        'LISTEN 0 128 127.0.0.1:8001 0.0.0.0:*\n'
                        'LISTEN 0 128 198.51.100.20:45789 0.0.0.0:*\n')
                return SimpleNamespace(returncode=0, stdout=text)
            return SimpleNamespace(returncode=0, stdout='')
        class HTTP:
            def open(self, url, **kwargs):
                requested.append(url)
                if url.endswith('/metrics'):
                    return io.BytesIO(b'vllm:num_requests_running{model_name="new"} 0\n')
                name = 'Qwen/Qwen3-Embedding-8B' if ':8001/' in url else 'New/Model'
                return io.BytesIO(json.dumps({'data': [{'id': name}]}).encode())
        process = SimpleNamespace(
            read_bytes=lambda: b'vllm serve New/Model --port 8123',
            parent=SimpleNamespace(joinpath=lambda name: SimpleNamespace(
                read_text=lambda **kwargs: 'Name:\tvllm\nThreads:\t42\n')),
        )
        out = io.StringIO()
        with patch('subprocess.run', run), patch('urllib.request.build_opener', return_value=HTTP()), \
             patch('pathlib.Path.glob', return_value=[process]), contextlib.redirect_stdout(out):
            exec(PROBE, {})
        result = json.loads(out.getvalue())
        self.assertEqual(len(result['models']), 2)
        self.assertEqual({m['kind'] for m in result['models']}, {'vllm', 'embedding'})
        self.assertFalse(any('45789' in url for url in requested), 'NCCL socket must not be probed')

    def test_published_custom_port_is_probed_without_touching_nccl(self):
        requested = []
        def run(args, **kwargs):
            if args[0] == 'ss':
                return SimpleNamespace(returncode=0, stdout='LISTEN 0 128 198.51.100.20:45789 0.0.0.0:*\n')
            if args[:2] == ['docker', 'ps']:
                return SimpleNamespace(returncode=0, stdout='abc\n')
            if args[:2] == ['docker', 'inspect']:
                settings = {'Ports': {'8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8123'}]},
                            'Networks': {'bridge': {'IPAddress': '198.51.100.20'}}}
                return SimpleNamespace(returncode=0, stdout=json.dumps(settings))
            return SimpleNamespace(returncode=0, stdout='')
        class HTTP:
            def open(self, url, **kwargs):
                requested.append(url)
                if url.endswith('/metrics'):
                    return io.BytesIO(b'vllm:num_requests_running 0\n')
                return io.BytesIO(json.dumps({'data': [{'id': 'new/model'}]}).encode())
        out = io.StringIO()
        with patch('subprocess.run', run), patch('urllib.request.build_opener', return_value=HTTP()), \
             patch('pathlib.Path.glob', return_value=[]), contextlib.redirect_stdout(out):
            exec(PROBE, {})
        result = json.loads(out.getvalue())
        self.assertIn('8123', requested[0])
        self.assertFalse(any('45789' in url for url in requested))
        self.assertEqual(result['models'][0]['port'], 8123)

    def test_process_metadata_covers_all_ports_and_default_port(self):
        def process(command, threads):
            return SimpleNamespace(
                read_bytes=lambda: command.encode(),
                parent=SimpleNamespace(joinpath=lambda name: SimpleNamespace(
                    read_text=lambda **kwargs: f'Name:\tvllm\nThreads:\t{threads}\n')),
            )
        processes = [
            process('vllm serve A --port 8123 --metrics-port 8124 '
                    '--http-port 8125 --max-num-seqs 7', 42),
            process('vllm serve B --max-batch 3', 9),
        ]
        def run(args, **kwargs):
            if args[0] == 'ss':
                text = ''.join(f'LISTEN 0 128 127.0.0.1:{port} 0.0.0.0:*\n'
                               for port in (8000, 8123, 8124, 8125))
                return SimpleNamespace(returncode=0, stdout=text)
            return SimpleNamespace(returncode=0, stdout='')
        class HTTP:
            def open(self, url, **kwargs):
                if url.endswith('/metrics'):
                    return io.BytesIO(b'vllm:num_requests_running 0\n')
                port = url.split(':')[2].split('/')[0]
                return io.BytesIO(json.dumps({'data': [{'id': 'model-' + port}]}).encode())
        out = io.StringIO()
        with patch('subprocess.run', run), patch('urllib.request.build_opener', return_value=HTTP()), \
             patch('pathlib.Path.glob', return_value=processes), contextlib.redirect_stdout(out):
            exec(PROBE, {})
        result = json.loads(out.getvalue())
        metadata = {model['port']: (model.get('capacity'), model.get('threads'))
                    for model in result['models']}
        self.assertEqual(set(metadata), {8000, 8123, 8124, 8125})
        self.assertEqual(metadata[8123], (7, 42))
        self.assertEqual(metadata[8124], (7, 42))
        self.assertEqual(metadata[8125], (7, 42))
        self.assertEqual(metadata[8000], (3, 9))

    def test_discover_rejects_bad_remote_forward_address(self):
        data = {'models': [dict(descriptor(), address='evil:host')], 'docker_ok': True}
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(data))):
            self.assertIn('error', discover('192.0.2.10', 'nvidia'))

    def test_model_views_and_metric_schema(self):
        models = [dict(kind='gb10'), dict(kind='embedding'), dict(kind='vllm')]
        self.assertEqual(len(monitor.selected_models(models, False)), 2)
        a, b = [monitor.model_metric_rows(dict(kind=k, values={}, history=monitor.History()))
                for k in ('gb10', 'vllm')]
        self.assertEqual([(n, note) for n, _, note in a], [(n, note) for n, _, note in b])

    def test_card_order_survives_missing_cards_and_moves(self):
        first = {'name': 'first'}
        second = {'name': 'second'}
        order = ['missing']
        monitor.sync_card_order([first, second], order)
        self.assertEqual(order, ['missing', 'first', 'second'])
        self.assertEqual([item['name'] for item in monitor.ordered_models([second, first], order)],
                         ['first', 'second'])
        monitor.move_card(order, [first, second], 'second', -1)
        self.assertEqual(order, ['missing', 'second', 'first'])
        self.assertEqual(monitor.ensure_card_focus([first, second], 'second'), 'second')
        self.assertEqual(monitor.ensure_card_focus([first], 'second'), 'first')
        self.assertIsNone(monitor.ensure_card_focus([], 'second'))

    def test_stale_cards_are_removed_after_180_seconds(self):
        old = {'name': 'old', 'last': 100}
        fresh = {'name': 'fresh', 'last': 200}
        created_only = {'name': 'created', 'created': 100}
        models = [old, fresh, created_only]
        closed = []
        removed = monitor.prune_stale_models(models, 280, closed.append)
        self.assertEqual([model['name'] for model in removed], ['old', 'created'])
        self.assertEqual([model['name'] for model in models], ['fresh'])
        self.assertEqual([model['name'] for model in closed], ['old', 'created'])

    def test_focused_card_has_a_marker(self):
        model = {'name': 'focused', 'kind': 'vllm', 'values': {},
                 'history': monitor.History(), 'last': 0, 'status': 'LIVE'}
        text = '\n'.join(monitor.model_tables([model], 100, False, 1,
                                              focus_key='focused'))
        self.assertIn('▶ focused', text)

    def test_vllm_static_capacity_and_threads_fill_missing_metrics(self):
        rows = monitor.model_metric_rows(dict(kind='vllm', values={},
                                              history=monitor.History(),
                                              capacity=8, threads=60))
        values = {name: value for name, value, _ in rows}
        self.assertEqual(values['Вместимость'], '8')
        self.assertEqual(values['Потоки процесса'], '60')

    def test_gb10_static_capacity_and_threads_fill_missing_metrics(self):
        rows = monitor.model_metric_rows(dict(kind='gb10', values={},
                                              history=monitor.History(),
                                              capacity=8, threads=60))
        values = {name: value for name, value, _ in rows}
        self.assertEqual(values['Вместимость'], '8')
        self.assertEqual(values['Потоки процесса'], '60')

    def test_gb10_without_discovery_metadata_is_not_fabricated(self):
        rows = monitor.model_metric_rows(dict(kind='gb10', values={},
                                              history=monitor.History()))
        values = {name: value for name, value, _ in rows}
        self.assertEqual(values['Вместимость'], 'нет данных')
        self.assertEqual(values['Потоки процесса'], 'нет данных')

    def test_hardware_table_uses_tailscale_names_not_addresses(self):
        hosts = [{'name': 'spark-a', 'ip': '192.0.2.10'}]
        hardware = {'192.0.2.10': (10.0, {'gpus': [['0', '42', '7', '12', '30']],
                                         'ram_used': 99.5, 'ram_total': 100.0,
                                         'swap_used': 1.0, 'load': '0.5'})}
        raw_rows = monitor.hardware_rows(hardware, hosts, 12.0)
        self.assertEqual(len(raw_rows), 2)
        self.assertIn('spark-a GPU 0', raw_rows[1])
        rows = monitor.framed_table('test', raw_rows, 100)
        text = '\n'.join(rows)
        self.assertIn('spark-a', text)
        self.assertNotIn('192.0.2.10', text)
        alerts = monitor.document_alerts(rows, hardware, hosts)
        self.assertTrue(any(severity == 'critical' for line in alerts for _, _, severity in line))


if __name__ == '__main__':
    unittest.main()
