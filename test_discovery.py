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
        process = SimpleNamespace(read_bytes=lambda: b'vllm serve New/Model --port 8123')
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

    def test_hardware_table_uses_tailscale_names_not_addresses(self):
        hosts = [{'name': 'spark-a', 'ip': '192.0.2.10'}]
        hardware = {'192.0.2.10': (10.0, {'gpus': [['0', '42', '7', '12', '30']],
                                         'ram_used': 99.5, 'ram_total': 100.0,
                                         'swap_used': 1.0, 'load': '0.5'})}
        rows = monitor.framed_table('test', monitor.hardware_rows(hardware, hosts, 12.0), 100)
        text = '\n'.join(rows)
        self.assertIn('spark-a', text)
        self.assertNotIn('192.0.2.10', text)
        alerts = monitor.document_alerts(rows, hardware, hosts)
        self.assertTrue(any(severity == 'critical' for line in alerts for _, _, severity in line))


if __name__ == '__main__':
    unittest.main()
