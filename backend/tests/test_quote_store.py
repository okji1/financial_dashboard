"""Exercise real cross-process SQLite snapshots with deterministic timestamps."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quote_store import read_snapshot, write_snapshot
from test_data_integrity import QUOTE
import gold_data

NOW = datetime.datetime(2026, 11, 12, tzinfo=datetime.timezone.utc)


class QuoteStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'quotes.sqlite')

    def test_missing_store_returns_none_without_creating_file(self):
        self.assertIsNone(read_snapshot(self.path, now=NOW))
        self.assertFalse(Path(self.path).exists())

    def test_success_is_visible_to_another_process(self):
        write_snapshot(self.path, QUOTE, now=NOW)
        script = 'import json,datetime,sys; from quote_store import read_snapshot; print(json.dumps(read_snapshot(sys.argv[1],now=datetime.datetime.fromisoformat(sys.argv[2]))))'
        result = subprocess.check_output([sys.executable, '-c', script, self.path, NOW.isoformat()], cwd=Path(__file__).resolve().parents[1], text=True)
        self.assertEqual(json.loads(result), QUOTE)

    def test_expired_and_failed_refresh_never_serve_old_signal(self):
        write_snapshot(self.path, QUOTE, now=NOW)
        self.assertIsNone(read_snapshot(self.path, now=NOW + datetime.timedelta(seconds=61)))
        write_snapshot(self.path, None, now=NOW)
        self.assertIsNone(read_snapshot(self.path, now=NOW))

    def test_corrupted_snapshot_fails_closed(self):
        Path(self.path).write_text('invalid sqlite')
        self.assertIsNone(read_snapshot(self.path, now=NOW))

    def test_invalid_prices_are_not_persisted(self):
        for value in [0, -1, float('nan'), float('inf'), True]:
            with self.assertRaises(ValueError):
                write_snapshot(self.path, {**QUOTE, 'usd_krw_rate': value}, now=NOW)

    def test_snapshot_mode_never_calls_provider(self):
        with patch.dict(os.environ, {'QUOTE_SNAPSHOT_PATH': self.path}), patch('gold_data._collect_gold_premium_data') as collect:
            self.assertIsNone(gold_data.get_gold_premium_data())
            collect.assert_not_called()

    def test_collector_persists_failures_instead_of_reusing_previous_quote(self):
        from collector import refresh_snapshot
        with patch('collector._collect_gold_premium_data', return_value=None):
            self.assertFalse(refresh_snapshot(self.path))
        self.assertIsNone(read_snapshot(self.path))

    def test_future_timestamp_is_rejected(self):
        write_snapshot(self.path, {**QUOTE, 'timestamp': (NOW + datetime.timedelta(seconds=10)).isoformat()}, now=NOW)
        self.assertIsNone(read_snapshot(self.path, now=NOW))

    def test_api_uses_snapshot_and_reports_unavailable_as_503(self):
        from app import app
        quote = {**QUOTE, 'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        with patch.dict(os.environ, {'QUOTE_SNAPSHOT_PATH': self.path}), patch('gold_data._collect_gold_premium_data') as collect:
            client = app.test_client()
            for endpoint in ('gold-premium', 'investment-strategy', 'gold-analysis'):
                self.assertEqual(client.get('/api/' + endpoint).status_code, 503)
            write_snapshot(self.path, quote)
            for endpoint in ('gold-premium', 'investment-strategy', 'gold-analysis'):
                self.assertEqual(client.get('/api/' + endpoint).status_code, 200)
            collect.assert_not_called()
