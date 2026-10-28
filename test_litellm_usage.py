import unittest

from litellm_usage import APIError, UsageClient


class FakeClient(UsageClient):
    def __init__(self, responses):
        super().__init__('http://example.test', 'key')
        self.responses = responses
        self.calls = []

    def get(self, path, **params):
        self.calls.append(path)
        result = self.responses[path]
        if isinstance(result, Exception):
            raise result
        return result


class ModelInfoTests(unittest.TestCase):
    def test_reads_model_routes(self):
        client = FakeClient({'/model/info': {'data': [{'model_name': 'route'}]}})
        self.assertEqual(client.model_info(), [{'model_name': 'route'}])

    def test_falls_back_to_v1_on_404(self):
        client = FakeClient({'/model/info': APIError(404),
                             '/v1/model/info': {'data': [{'model_name': 'route'}]}})
        self.assertEqual(client.model_info(), [{'model_name': 'route'}])
        self.assertEqual(client.calls, ['/model/info', '/v1/model/info'])

    def test_forbidden_route_has_actionable_message(self):
        client = FakeClient({'/model/info': APIError(403)})
        with self.assertRaisesRegex(RuntimeError, 'нужен доступ к параметрам провайдера'):
            client.model_info()

    def test_fallback_forbidden_route_has_actionable_message(self):
        client = FakeClient({'/model/info': APIError(404),
                             '/v1/model/info': APIError(403)})
        with self.assertRaisesRegex(RuntimeError, 'нужен доступ к параметрам провайдера') as ctx:
            client.model_info()
        self.assertIn('/v1/model/info', str(ctx.exception))
        self.assertEqual(client.calls, ['/model/info', '/v1/model/info'])

    def test_non_404_error_propagates_without_fallback(self):
        client = FakeClient({'/model/info': APIError(500)})
        with self.assertRaises(APIError) as ctx:
            client.model_info()
        self.assertEqual(ctx.exception.status, 500)
        self.assertEqual(client.calls, ['/model/info'])

    def test_fallback_non_404_error_propagates(self):
        client = FakeClient({'/model/info': APIError(404),
                             '/v1/model/info': APIError(401)})
        with self.assertRaises(APIError) as ctx:
            client.model_info()
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(client.calls, ['/model/info', '/v1/model/info'])

    def test_normalizes_malformed_nested_fields(self):
        client = FakeClient({'/model/info': {'data': [
            {'model_name': 'malformed', 'litellm_params': ['not', 'a', 'dict'],
             'model_info': 'not-a-dict'},
            {'model_name': 'nulls', 'litellm_params': None, 'model_info': None},
            {'model_name': 'valid', 'litellm_params': {'model': 'upstream'},
             'model_info': {'id': 'route-id'}},
            {'model_name': 'no-nested-fields'},
        ]}})
        routes = client.model_info()
        self.assertEqual(routes[0], {'model_name': 'malformed',
                                     'litellm_params': {}, 'model_info': {}})
        self.assertEqual(routes[1], {'model_name': 'nulls',
                                     'litellm_params': {}, 'model_info': {}})
        self.assertEqual(routes[2], {'model_name': 'valid',
                                     'litellm_params': {'model': 'upstream'},
                                     'model_info': {'id': 'route-id'}})
        self.assertEqual(routes[3], {'model_name': 'no-nested-fields'})

    def test_rejects_unknown_payload_shape(self):
        client = FakeClient({'/model/info': {'data': [1]}})
        with self.assertRaisesRegex(ValueError, 'неизвестный формат'):
            client.model_info()


class KeyAliasTests(unittest.TestCase):
    def test_returns_current_key_alias(self):
        client = FakeClient({'/key/info': {'info': {'key_alias': 'team-key'}}})
        self.assertEqual(client.key_alias(), 'team-key')
        self.assertEqual(client.calls, ['/key/info'])
        # Read-only: catalog/per-key state stays untouched.
        self.assertIsNone(client._catalog)
        self.assertIsNone(client._personal_key)

    def test_forbidden_key_info_returns_empty(self):
        client = FakeClient({'/key/info': APIError(403)})
        self.assertEqual(client.key_alias(), '')

    def test_transport_error_returns_empty(self):
        client = FakeClient({'/key/info': RuntimeError('нет соединения')})
        self.assertEqual(client.key_alias(), '')

    def test_key_hash_alias_returns_empty(self):
        client = FakeClient({'/key/info': {'info': {'key_alias': 'key-hash-a1b2c3'}}})
        self.assertEqual(client.key_alias(), '')

    def test_empty_alias_returns_empty(self):
        client = FakeClient({'/key/info': {'info': {'key_alias': '   '}}})
        self.assertEqual(client.key_alias(), '')

    def test_malformed_payloads_return_empty(self):
        payloads = (
            None,
            [],
            'not-a-dict',
            {},
            {'info': None},
            {'info': []},
            {'info': {}},
            {'info': {'key_alias': None}},
            {'info': {'key_alias': 42}},
            {'info': {'key_alias': ['team-key']}},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                client = FakeClient({'/key/info': payload})
                self.assertEqual(client.key_alias(), '')

    def test_cleans_whitespace_and_control_characters(self):
        client = FakeClient({'/key/info': {
            'info': {'key_alias': '  team-key\t\n\x00  team  '}}})
        self.assertEqual(client.key_alias(), 'team-key team')

    def test_caps_alias_at_64_characters(self):
        client = FakeClient({'/key/info': {'info': {'key_alias': 'a' * 100}}})
        alias = client.key_alias()
        self.assertEqual(alias, 'a' * 64)
        self.assertEqual(len(alias), 64)


if __name__ == '__main__':
    unittest.main()
