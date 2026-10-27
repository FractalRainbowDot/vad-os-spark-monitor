import unittest
from unittest.mock import patch

import settings


class ArgumentTests(unittest.TestCase):
    def test_parse_equals_space_boolean_and_positional(self):
        flags, positional = settings.parse_flags(
            ['vllm', 'serve', '/model', '--port=8000', '--max-model-len', '32768',
             '--enforce-eager'])
        self.assertEqual(positional, ['vllm', 'serve', '/model'])
        self.assertEqual(flags, [('--port', '8000'), ('--max-model-len', '32768'),
                                 ('--enforce-eager', '')])

    def test_model_name_prefers_served_name(self):
        flags, positional = settings.parse_flags(
            ['--model', '/models/local-dir', '--served-model-name', 'Org/Public-Name'])
        self.assertEqual(settings._model_name(flags, positional), 'Org/Public-Name')

    def test_redaction_covers_separate_and_equals_forms(self):
        argv = settings._redact(['vllm', '--api-key', 'SECRET', '--token=OTHER',
                                 '--model', '/model'])
        text = ' '.join(argv)
        self.assertNotIn('SECRET', text)
        self.assertNotIn('OTHER', text)
        self.assertIn('--model /model', text)


SAMPLE = {
    'docker_ok': True,
    'containers': [{
        'name': 'engine', 'image': 'image:tag',
        'cmd': ['vllm', 'serve', '/model', '--served-model-name', 'Org/Model',
                '--host', '0.0.0.0', '--port', '8000',
                '--tensor-parallel-size', '2', '--max-model-len', '32768',
                '--max-num-seqs', '8', '--gpu-memory-utilization', '0.5',
                '--kv-cache-memory-bytes', '10737418240', '--kv-cache-dtype', 'fp8',
                '--enforce-eager', '--api-key', 'SECRET'],
        'started': '2026-10-27T10:00:00.123Z',
        'ports': {'8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8001'}]},
    }],
    'processes': [
        {'argv': ['vllm', 'serve', '/model', '--served-model-name', 'Org/Model',
                  '--host', '0.0.0.0', '--port', '8000', '--tensor-parallel-size', '2']},
        {'argv': ['/opt/gb10_inference', '--server', '--model-dir', '/models/Qwen',
                  '--max-seq-len', '131072', '--max-batch', '8', '--kv-cache', 'q8']},
    ],
}


class SettingsTests(unittest.TestCase):
    def test_deduplicates_container_and_host_process(self):
        found = settings.entries(SAMPLE)
        self.assertEqual([entry['model'] for entry in found], ['Org/Model', 'Qwen'])
        self.assertEqual(found[0]['source'], 'контейнер')
        self.assertEqual(found[1]['source'], 'процесс')

    def test_curated_values_and_published_address(self):
        entry = settings.entries(SAMPLE)[0]
        rows = dict(settings.curated(entry))
        self.assertEqual(rows['Контекст'], '32768')
        self.assertEqual(rows['TP / PP'], '2 / —')
        self.assertEqual(rows['GPU memory'], '50%')
        self.assertEqual(rows['KV-cache'], '10.00 GiB · fp8')
        self.assertEqual(rows['Адрес'], '127.0.0.1:8001 → 8000')
        self.assertEqual(rows['Флаги'], 'enforce-eager')

    def test_table_contains_all_flags_and_no_secret(self):
        snapshot = {'entries': settings.entries(SAMPLE), 'error': None}
        text = '\n'.join(settings.settings_table('spark-test', snapshot, 100))
        self.assertIn('━ ВСЕ ФЛАГИ ЗАПУСКА', text)
        self.assertIn('--tensor-parallel-size 2', text)
        self.assertIn('--api-key <REDACTED>', text)
        self.assertNotIn('SECRET', text)

    def test_document_uses_ip_keys_and_reports_errors(self):
        hosts = [{'name': 'spark-a', 'ip': '192.0.2.1'},
                 {'name': 'spark-b', 'ip': '192.0.2.2'}]
        cache = {'192.0.2.1': (0, {'entries': settings.entries(SAMPLE), 'error': None})}
        errors = {'192.0.2.2': 'SSH/опрос недоступен'}
        text = '\n'.join(settings.settings_document(hosts, cache, errors, 100, 0))
        self.assertIn('╭ spark-a · модели: 2', text)
        self.assertIn('НЕТ СВЕЖИХ ДАННЫХ: SSH/опрос недоступен', text)

    def test_read_settings_error_is_contained(self):
        with patch('settings._run', side_effect=RuntimeError('down')):
            snapshot = settings.read_settings('192.0.2.1', 'nvidia')
        self.assertEqual(snapshot['entries'], [])
        self.assertEqual(snapshot['error'], 'SSH/опрос недоступен')

    def test_process_only_server_is_visible(self):
        raw = {'containers': [], 'processes': SAMPLE['processes'][1:]}
        found = settings.entries(raw)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['engine'], 'gb10')
        self.assertEqual(found[0]['model'], 'Qwen')

    def test_two_containers_with_same_identity_are_both_kept(self):
        second = dict(SAMPLE['containers'][0], name='engine-2',
                      ports={'8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8002'}]})
        raw = {'containers': [SAMPLE['containers'][0], second], 'processes': []}
        found = settings.entries(raw)
        self.assertEqual([entry['name'] for entry in found], ['engine', 'engine-2'])


if __name__ == '__main__':
    unittest.main()
