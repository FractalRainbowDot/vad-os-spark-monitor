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


PROVIDER = {
    'model_name': 'openai/DeepSeek-V4.1-Flash-1017',
    'litellm_params': {
        'custom_llm_provider': 'openai',
        'model': 'openai/DeepSeek-V4.1-Flash-1017',
        'api_base': 'http://user:pass@192.0.2.2:9000/v1',
        'api_key': 'SECRET',
        'input_cost_per_token': 2e-8,
        'output_cost_per_token': 1e-6,
        'tags': ['prod'],
    },
    'model_info': {
        'id': 'route-id',
        'max_input_tokens': 229376,
        'max_output_tokens': 32768,
        'rpm': 100,
        'tpm': 1000,
        'blocked': False,
        'direct_access': True,
        'key': 'KEYHASH',
        'mode': 'chat',
        'description': 'demo route',
    },
}


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

    def test_provider_rows_format_costs_and_redact_secrets(self):
        rows = dict(settings.provider_rows(PROVIDER))
        self.assertEqual(rows['Провайдер'], 'openai')
        self.assertEqual(rows['Вход / выход'], '229376 / 32768')
        self.assertEqual(rows['RPM / TPM'], '100 / 1000')
        self.assertEqual(rows['Стоимость'], '$0.02 / 1M вход · $1 / 1M выход')
        self.assertEqual(rows['Заблокирован'], 'нет')
        self.assertNotIn('user:pass', rows['API base'])
        self.assertIn('<скрыто>', rows['API base'])

    def test_provider_table_lists_all_parameters_without_secrets(self):
        text = '\n'.join(settings.provider_table(PROVIDER, 110))
        self.assertIn('━ ВСЕ ПАРАМЕТРЫ ПРОВАЙДЕРА', text)
        self.assertIn('api_key <скрыто>', text)
        self.assertIn('key <скрыто>', text)
        self.assertIn('input_cost_per_token 2e-08', text)
        self.assertNotIn('SECRET', text)
        self.assertNotIn('KEYHASH', text)
        self.assertNotIn('user:pass', text)

    def test_provider_document_states_and_settings_document_option(self):
        self.assertIn('Загрузка параметров провайдера', '\n'.join(
            settings.provider_document(None, '', 100)))
        self.assertIn('НЕТ ДАННЫХ: 403', '\n'.join(
            settings.provider_document(None, '403', 100)))
        self.assertIn('Маршруты провайдера не найдены', '\n'.join(
            settings.provider_document([], '', 100)))
        cache = {'192.0.2.1': (0, {'entries': settings.entries(SAMPLE), 'error': None})}
        hosts = [{'name': 'spark-a', 'ip': '192.0.2.1'}]
        text = '\n'.join(settings.settings_document(
            hosts, cache, {}, 110, 0, providers=[PROVIDER],
            provider_error='', include_provider=True))
        self.assertIn('ПРОВАЙДЕР · openai/DeepSeek-V4.1-Flash-1017', text)
        self.assertIn('╭ spark-a · модели: 2', text)

    def test_provider_only_document_omits_spark_tables(self):
        cache = {'192.0.2.1': (0, {'entries': settings.entries(SAMPLE), 'error': None})}
        hosts = [{'name': 'spark-a', 'ip': '192.0.2.1'}]
        text = '\n'.join(settings.settings_document(
            hosts, cache, {}, 110, 0, providers=[PROVIDER],
            provider_error='', include_provider=True, include_sparks=False))
        self.assertIn('ПРОВАЙДЕР · openai/DeepSeek-V4.1-Flash-1017', text)
        self.assertNotIn('spark-a', text)
        self.assertNotIn('ВСЕ ФЛАГИ ЗАПУСКА', text)
        self.assertNotIn('Загрузка настроек', text)

    def test_spark_only_document_omits_provider_tables(self):
        cache = {'192.0.2.1': (0, {'entries': settings.entries(SAMPLE), 'error': None})}
        hosts = [{'name': 'spark-a', 'ip': '192.0.2.1'}]
        text = '\n'.join(settings.settings_document(
            hosts, cache, {}, 110, 0, providers=[PROVIDER],
            provider_error='', include_provider=False, include_sparks=True))
        self.assertIn('╭ spark-a · модели: 2', text)
        self.assertNotIn('ПРОВАЙДЕР ·', text)
        self.assertNotIn('ВСЕ ПАРАМЕТРЫ ПРОВАЙДЕРА', text)

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


class ProviderSanitizationTests(unittest.TestCase):
    def test_secret_key_normalizes_case_and_hyphens(self):
        for name in ('vertex_credentials', 'aws_secret_access_key', 'secret_key',
                     'private_key', 'master_key', 'refresh_token', 'id_token',
                     'session_token', 'bearer_token', 'azure_ad_token',
                     'X-Api-Key', 'x-api-key', 'Authorization'):
            with self.subTest(name=name):
                self.assertTrue(settings._secret_key(name))
        for name in ('max_tokens', 'max_input_tokens', 'max_output_tokens',
                     'input_cost_per_token', 'output_cost_per_token',
                     'cache_read_input_token_cost', 'cache_creation_input_token_cost',
                     'key_alias', 'tokenizer', 'tokenizer_name',
                     'use_xai_oauth'):
            with self.subTest(name=name):
                self.assertFalse(settings._secret_key(name))

    def test_json_string_headers_are_recursively_redacted(self):
        value = settings._sanitize(
            '{"X-Api-Key":"HEADER_SECRET","Authorization":"Bearer BEARER_SECRET"}',
            'extra_headers')
        self.assertEqual(value, {'X-Api-Key': '<скрыто>',
                                 'Authorization': '<скрыто>'})

    def test_url_userinfo_and_query_credentials_are_redacted(self):
        value = settings._sanitize(
            'https://user:pass@host/v1?api_key=QUERY_SECRET&token=QUERY_TOKEN&model=x')
        self.assertNotIn('user:pass', value)
        self.assertNotIn('QUERY_SECRET', value)
        self.assertNotIn('QUERY_TOKEN', value)
        self.assertIn('model=x', value)

    def test_auth_schemes_and_common_prefixes_are_redacted(self):
        self.assertEqual(settings._sanitize('Basic dXNlcjpwYXNz'), '<скрыто>')
        self.assertEqual(settings._sanitize('Bearer abc123'), '<скрыто>')
        embedded = settings._sanitize('prefix Bearer abc123DEF suffix')
        self.assertIn('<скрыто>', embedded)
        self.assertNotIn('abc123DEF', embedded)
        for value in ('gsk_' + 'A' * 20, 'AIza' + 'B' * 20,
                      'AKIAIOSFODNN7EXAMPLE', 'sk-' + 'd' * 20, 'hf_' + 'e' * 20):
            with self.subTest(value=value):
                self.assertEqual(settings._sanitize(value), '<скрыто>')

    def test_plain_text_strips_control_characters_and_newlines(self):
        self.assertEqual(settings._plain_text('bad\x1b[31m\nnext'), 'bad next')
        self.assertEqual(settings._plain_text('a\tb\r\nc'), 'a b c')
        self.assertNotIn('\x1b', settings._sanitize('red\x1b[31m'))

    def test_provider_params_skip_empty_strings(self):
        provider = {'litellm_params': {'empty_value': '', 'blank_value': '   ',
                                       'api_key': 'SECRET'},
                    'model_info': {}}
        keys = [key for key, _ in settings.provider_params(provider)]
        self.assertNotIn('empty_value', keys)
        self.assertNotIn('blank_value', keys)
        self.assertIn('api_key', keys)

    def test_provider_table_hides_secrets_and_control_characters(self):
        provider = {
            'model_name': 'route\x1b[31m\nname',
            'litellm_params': {
                'custom_llm_provider': 'vertex_ai',
                'vertex_credentials': '{"type":"service_account","private_key":"PRIVATE_SECRET"}',
                'aws_secret_access_key': 'AWS_SECRET_VALUE',
                'extra_headers': '{"X-Api-Key":"HEADER_SECRET"}',
                'api_base': 'https://api.example.com/v1?api_key=QUERY_SECRET',
                'auth_header': 'Basic BASIC_SECRET',
                'notes': 'gsk_GSK_SECRET_VALUE AIzaAIZA_SECRET_VALUE '
                         'AKIAIOSFODNN7EXAMPLE',
                'empty_value': '',
                'input_cost_per_token': 2e-8,
                'output_cost_per_token': 1e-6,
                'max_tokens': 4096,
                'key_alias': 'public-alias',
                'tokenizer_name': 'tiktoken',
                'param\x1b[2Jname': 'plain',
            },
            'model_info': {'id': 'route-id'},
        }
        text = '\n'.join(settings.provider_table(provider, 120))
        for secret in ('PRIVATE_SECRET', 'AWS_SECRET_VALUE', 'HEADER_SECRET',
                       'QUERY_SECRET', 'BASIC_SECRET', 'GSK_SECRET_VALUE',
                       'AIZA_SECRET_VALUE', 'AKIAIOSFODNN7EXAMPLE'):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, text)
        self.assertNotIn('\x1b', text)
        self.assertIn('input_cost_per_token 2e-08', text)
        self.assertIn('output_cost_per_token 1e-06', text)
        self.assertIn('max_tokens 4096', text)
        self.assertIn('key_alias public-alias', text)
        self.assertIn('tokenizer_name tiktoken', text)
        self.assertIn('paramname plain', text)
        self.assertNotIn('empty_value', text)


if __name__ == '__main__':
    unittest.main()
