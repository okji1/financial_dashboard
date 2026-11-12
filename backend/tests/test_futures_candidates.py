"""Offline tests for safe KIS gold-futures contract discovery."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from futures_api import generate_gold_futures_candidates, find_active_gold_contract

class FuturesCandidateTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_empty_config_does_not_fabricate_index_futures(self):
        self.assertEqual(generate_gold_futures_candidates(), [])
        self.assertIsNone(find_active_gold_contract())

    @patch.dict(os.environ, {"KIS_GOLD_FUTURES_SYMBOLS": "ABCDE1, FGHIJ2,ABCDE1"})
    def test_configured_symbols_are_deduplicated(self):
        self.assertEqual(
            [x["symbol"] for x in generate_gold_futures_candidates()],
            ["ABCDE1", "FGHIJ2"],
        )

    @patch.dict(os.environ, {"KIS_GOLD_FUTURES_SYMBOLS": "NOT VALID!"})
    def test_invalid_symbol_fails_closed(self):
        with self.assertRaises(ValueError):
            generate_gold_futures_candidates()

if __name__ == "__main__":
    unittest.main()
