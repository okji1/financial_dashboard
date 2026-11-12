"""Offline tests for KRX daily gold provider (no credentials/network needed)."""
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.krx_gold import KRXGoldError, get_krx_gold_quote


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, headers, params, timeout):
        self.calls.append((url, headers, params, timeout))
        return FakeResponse(self.payloads.pop(0))


def row(close="177290", day="20261110", code="04020000"):
    return {"ISU_CD": code, "BAS_DD": day, "TDD_CLSPRC": close}


class KRXGoldProviderTests(unittest.TestCase):
    @patch.dict(os.environ, {"KRX_API_KEY": "test-key"})
    def test_parses_1kg_and_ignores_mini_gold(self):
        session = FakeSession([{"OutBlock_1": [
            row("177900", code="04020100"), row("177290")
        ]}])
        quote = get_krx_gold_quote("20261110", session=session, lookback_days=0)
        self.assertEqual(quote["close_krw_per_g"], 177290)
        self.assertEqual(quote["trade_date"], "20261110")
        self.assertEqual(quote["symbol"], "04020000")
        self.assertFalse(quote["is_realtime"])
        self.assertEqual(session.calls[0][1], {"AUTH_KEY": "test-key"})
        self.assertEqual(session.calls[0][2], {"basDd": "20261110"})

    @patch.dict(os.environ, {"KRX_API_KEY": "test-key"})
    def test_falls_back_to_previous_trading_day(self):
        session = FakeSession([
            {"OutBlock_1": []},
            {"OutBlock_1": [row(day="20261110")]},
        ])
        result = get_krx_gold_quote(date(2026, 11, 11), session=session, lookback_days=1)
        self.assertEqual(result["trade_date"], "20261110")
        self.assertEqual(len(session.calls), 2)

    @patch.dict(os.environ, {"KRX_API_KEY": "test-key"})
    def test_no_data_fails_without_fabricating_price(self):
        session = FakeSession([{"OutBlock_1": []}])
        with self.assertRaises(KRXGoldError):
            get_krx_gold_quote("20261110", session=session, lookback_days=0)

    @patch.dict(os.environ, {"KRX_API_KEY": "test-key"})
    def test_malformed_price_fails_closed(self):
        session = FakeSession([{"OutBlock_1": [row(close="not-a-price")]}])
        with self.assertRaises(KRXGoldError):
            get_krx_gold_quote("20261110", session=session, lookback_days=0)

    @patch.dict(os.environ, {"KRX_API_KEY": "test-key"})
    def test_malformed_response_fails_closed(self):
        session = FakeSession([{"error": "not authorized"}])
        with self.assertRaises(KRXGoldError):
            get_krx_gold_quote("20261110", session=session, lookback_days=0)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key_fails_closed(self):
        with self.assertRaises(KRXGoldError):
            get_krx_gold_quote("20261110", session=FakeSession([]))


if __name__ == "__main__":
    unittest.main()
