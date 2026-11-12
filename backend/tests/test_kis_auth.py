"""Offline regression tests for shared/local KIS token cache."""
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kis_auth


class KISTokenTests(unittest.TestCase):
    def setUp(self):
        kis_auth.clear_memory_cache()

    def tearDown(self):
        kis_auth.clear_memory_cache()

    @patch.object(kis_auth, "get_cached_token", return_value="db-token")
    @patch.object(kis_auth, "get_kis_token")
    def test_reuses_database_token(self, issue, stored):
        self.assertEqual(kis_auth.get_access_token(), "db-token")
        self.assertEqual(kis_auth.get_access_token(), "db-token")
        stored.assert_called_once_with(strict=True)
        issue.assert_not_called()

    @patch.object(kis_auth, "get_cached_token", side_effect=OSError("dns"))
    @patch.object(kis_auth, "get_kis_token")
    def test_db_failure_does_not_issue_new_token(self, issue, stored):
        self.assertIsNone(kis_auth.get_access_token())
        self.assertIsNone(kis_auth.get_access_token())
        stored.assert_called_once()
        issue.assert_not_called()

    @patch.object(kis_auth, "save_token", return_value=False)
    @patch.object(kis_auth, "get_cached_token", return_value=None)
    @patch.object(kis_auth, "get_kis_token", return_value="new-token")
    def test_failed_persist_still_reuses_memory(self, issue, stored, save):
        self.assertEqual(kis_auth.get_access_token(), "new-token")
        self.assertEqual(kis_auth.get_access_token(), "new-token")
        issue.assert_called_once()
        save.assert_called_once_with("new-token")

    @patch.object(kis_auth, "get_cached_token", return_value=None)
    @patch.object(kis_auth, "get_kis_token", return_value=None)
    def test_failed_issuance_has_cooldown(self, issue, stored):
        self.assertIsNone(kis_auth.get_access_token())
        self.assertIsNone(kis_auth.get_access_token())
        issue.assert_called_once()
        stored.assert_called_once()

    @patch.object(kis_auth, "save_token", return_value=True)
    @patch.object(kis_auth, "get_cached_token", return_value=None)
    @patch.object(kis_auth, "get_kis_token", return_value="one-token")
    def test_concurrent_threads_only_issue_once(self, issue, stored, save):
        results = []
        workers = [threading.Thread(target=lambda: results.append(kis_auth.get_access_token())) for _ in range(10)]
        for thread in workers:
            thread.start()
        for thread in workers:
            thread.join()
        self.assertEqual(results, ["one-token"] * 10)
        issue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
