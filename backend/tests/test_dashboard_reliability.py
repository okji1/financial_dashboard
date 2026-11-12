"""Regression coverage for repeated dashboard polling and preview CORS."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gold_data
from app import app


class DashboardReliabilityTests(unittest.TestCase):
    def test_gold_quote_cache_avoids_repeated_upstream_requests(self):
        gold_data._gold_cache = None
        gold_data._gold_cache_until = 0
        try:
            with patch.object(gold_data, "_collect_gold_premium_data", return_value={"premium_percentage": 1.0}) as collect:
                first = gold_data.get_gold_premium_data()
                second = gold_data.get_gold_premium_data()
                self.assertEqual(first, second)
                collect.assert_called_once()
        finally:
            gold_data._gold_cache = None
            gold_data._gold_cache_until = 0

    def test_vercel_preview_origin_is_allowed(self):
        with patch("app.start_background_updates"):
            response = app.test_client().get(
                "/api/futures-candidates",
                headers={"Origin": "https://financial-dashboard-9hz0t9gl4-kim-juins-projects.vercel.app"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "https://financial-dashboard-9hz0t9gl4-kim-juins-projects.vercel.app",
        )

    def test_unrelated_origin_is_not_allowed(self):
        with patch("app.start_background_updates"):
            response = app.test_client().get(
                "/api/futures-candidates",
                headers={"Origin": "https://untrusted.example.org"},
            )
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)


if __name__ == "__main__":
    unittest.main()
