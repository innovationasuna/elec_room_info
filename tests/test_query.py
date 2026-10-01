import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
from elec_room_info.utils.query import (
    AuthenticationError, ElecRoomQuery, QueryError, extract_balance, get_bearer_token,
)
from elec_room_info.utils.record_csv import CSVRecordHandler
from main import ElecRoomInfo


def response(information=None, status=200, body=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body if body is not None else {
        "map": {"showData": {"信息": information}}
    }).encode()
    return result


class QueryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        dotenv = patch('elec_room_info.utils.query.DOTENV_PATH', self.path / '.env')
        dotenv.start()
        self.addCleanup(dotenv.stop)
        self.config = {
            'query': {'bearer_token': 'test-only-token'},
            'record_csv': {'csv_file_path': str(self.path / 'records.csv')},
        }

    def test_token_precedence_and_prefix(self):
        self.assertEqual(get_bearer_token(self.config), 'test-only-token')
        (self.path / '.env').write_text('BEARER_TOKEN="Bearer dotenv-test-token"\n')
        self.assertEqual(get_bearer_token(self.config), 'dotenv-test-token')
        with patch.dict(os.environ, {'BEARER_TOKEN': 'env-test-token'}):
            self.assertEqual(get_bearer_token(self.config), 'env-test-token')
        # Loading the token must not copy it into persistent YAML config.
        self.assertEqual(self.config['query']['bearer_token'], 'test-only-token')

    def test_missing_and_placeholder_tokens(self):
        for token in ('', None, '<token>', 'Bearer ', 'token\nother'):
            with self.subTest(token=token):
                self.config['query']['bearer_token'] = token
                with self.assertRaises(AuthenticationError):
                    ElecRoomQuery(config=self.config)

    def test_timeout_configuration(self):
        for timeout in (0, -1, float('nan'), float('inf')):
            self.config['query']['timeout_seconds'] = timeout
            with self.assertRaises(ValueError):
                ElecRoomQuery(config=self.config)

    def test_numeric_values_and_units(self):
        samples = [('房间当前剩余电量：12.50度', 12.5), ('0', 0),
                   ('房间当前剩余电量 -0.5 kWh', -0.5), ('￥5.25 元', 5.25)]
        for text, expected in samples:
            with self.subTest(text=text):
                self.assertEqual(extract_balance(text, '房间当前剩余电量'), expected)
        self.assertEqual(extract_balance('剩余水费房间123, 4.5', '剩余水费', True), 4.5)

    def test_invalid_text_is_not_zero(self):
        for text in ('请先绑定房间', '', 'nan', 'inf', '房间123余额5', '1,234', '1e309', None):
            with self.subTest(text=text):
                with self.assertRaises(QueryError):
                    extract_balance(text, '房间当前剩余电量')

    @patch('elec_room_info.utils.query.requests.get')
    def test_real_upstream_dict_shape_and_timeout(self, get):
        get.return_value = response('房间当前剩余电量12.5')
        query = ElecRoomQuery(config=self.config)
        self.assertEqual(query.query_elec_room_info(1), '房间当前剩余电量12.5')
        self.assertEqual(get.call_args.kwargs['timeout'], 20)
        self.assertEqual(get.call_args.kwargs['headers']['synjones-auth'], 'Bearer test-only-token')

    @patch('elec_room_info.utils.query.requests.get')
    def test_auth_errors_at_http_and_business_levels(self, get):
        for reply in (response(status=401), response(status=403),
                      response(body={'code': 401}), response(body={'code': '403'})):
            get.return_value = reply
            with self.assertRaises(AuthenticationError):
                ElecRoomQuery(config=self.config).query_elec_room_info(1)

    @patch('elec_room_info.utils.query.requests.get')
    def test_timeout_and_bad_response(self, get):
        get.side_effect = requests.Timeout('test timeout')
        with self.assertRaises(QueryError):
            ElecRoomQuery(config=self.config).query_elec_room_info(1)
        get.side_effect = None
        for reply in (response(body={}), response(body={'map': None}),
                      response(body=[]), response(None), response(''), response(status=500)):
            get.return_value = reply
            with self.assertRaises(QueryError):
                ElecRoomQuery(config=self.config).query_elec_room_info(1)
        reply = response()
        reply._content = b'<html>login required</html>'
        get.return_value = reply
        with self.assertRaises(QueryError):
            ElecRoomQuery(config=self.config).query_elec_room_info(1)

    @patch('elec_room_info.utils.query.requests.get')
    def test_failed_batch_keeps_existing_csv(self, get):
        path = Path(self.config['record_csv']['csv_file_path'])
        path.write_text('existing history\n')
        get.side_effect = [response('12'), response(status=401)]
        with self.assertRaises(AuthenticationError):
            ElecRoomQuery(config=self.config).record_data()
        self.assertEqual(path.read_text(), 'existing history\n')

    @patch('elec_room_info.utils.query.requests.get')
    def test_successful_batch_records_numeric_data(self, get):
        get.side_effect = [response('房间当前剩余电量12.5'),
                           response('房间当前剩余金额8'), response('剩余水费room,0')]
        ElecRoomQuery(config=self.config).record_data()
        latest = CSVRecordHandler(self.config['record_csv']['csv_file_path']).get_latest()
        self.assertEqual(latest['electricity_balance'], 12.5)
        self.assertEqual(latest['air_conditioner_balance'], 8)
        self.assertEqual(latest['water_balance'], 0)

    @patch('elec_room_info.utils.query.requests.get')
    def test_env_token_update_used_next_request(self, get):
        get.return_value = response('1')
        query = ElecRoomQuery(config=self.config)
        with patch.dict(os.environ, {'BEARER_TOKEN': 'updated-test-token'}):
            query.query_elec_room_info(1)
        self.assertEqual(get.call_args.kwargs['headers']['synjones-auth'], 'Bearer updated-test-token')

    def test_query_failure_skips_alerts_and_next_round_recovers(self):
        app = ElecRoomInfo.__new__(ElecRoomInfo)
        app._query = Mock()
        app._query.record_data.side_effect = [QueryError('temporary failure'), None]
        app._monitor = Mock()
        app._query_interval = 1200
        with patch('main.time.sleep', side_effect=[None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                app.run()
        self.assertEqual(app._query.record_data.call_count, 2)
        app._monitor.once.assert_called_once_with()

    def test_csv_header_only_and_multiple_rows(self):
        recorder = CSVRecordHandler(self.config['record_csv']['csv_file_path'])
        self.assertIsNone(recorder.get_latest())
        for number in (1, 2, 3):
            recorder.record({'timestamp': '2026-10-01', 'water_balance': number,
                             'electricity_balance': number * 10, 'air_conditioner_balance': 0})
        self.assertEqual(recorder.get_latest()['electricity_balance'], 30)
        self.assertEqual(recorder.get_last_second()['electricity_balance'], 20)


if __name__ == '__main__':
    unittest.main()
