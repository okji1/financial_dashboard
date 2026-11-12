"""RSS worker offline security and persistence tests."""
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content.ingest import FeedSource, ingest_sources, validate_feed_url, fetch_feed_xml
from content.storage import upsert_article_metadata
from content.worker import run_worker


def public_dns(host, port, *, type):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]


def private_dns(host, port, *, type):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]


RSS = b'<rss><channel><item><title>Gold</title><link>https://example.org/gold</link></item></channel></rss>'


class IngestTests(unittest.TestCase):
    def test_rejects_unlisted_host(self):
        with self.assertRaises(ValueError):
            validate_feed_url("https://evil.example/rss", allowed_hosts=frozenset({"feeds.example.org"}), resolver=public_dns)

    def test_rejects_private_dns_and_custom_port(self):
        with self.assertRaises(ValueError):
            validate_feed_url("https://feeds.example.org/rss", allowed_hosts=frozenset({"feeds.example.org"}), resolver=private_dns)
        with self.assertRaises(ValueError):
            validate_feed_url("https://feeds.example.org:8443/rss", allowed_hosts=frozenset({"feeds.example.org"}), resolver=public_dns)

    def test_dry_run_never_writes(self):
        sink = Mock(side_effect=AssertionError("should not write"))
        report = ingest_sources([FeedSource("id1", "test", "https://feeds.example.org/rss")],
            allowed_hosts=frozenset({"feeds.example.org"}),
            fetcher=lambda url, **kwargs: RSS, sink=sink, dry_run=True)
        self.assertEqual(report["items"], 1)
        self.assertEqual(report["saved"], 0)
        sink.assert_not_called()

    def test_write_calls_sink_and_reports_count(self):
        sink = Mock(return_value=1)
        report = ingest_sources([FeedSource("id1", "test", "https://feeds.example.org/rss")],
            allowed_hosts=frozenset({"feeds.example.org"}),
            fetcher=lambda url, **kwargs: RSS, sink=sink, dry_run=False)
        self.assertEqual(report["saved"], 1)
        self.assertEqual(sink.call_count, 1)

    def test_failures_are_isolated_between_feeds(self):
        def fetch(url, **kwargs):
            if url.endswith("bad"):
                raise ValueError("unavailable")
            return RSS
        report = ingest_sources([
            FeedSource("bad", "bad", "https://feeds.example.org/bad"),
            FeedSource("ok", "ok", "https://feeds.example.org/good")
        ], allowed_hosts=frozenset({"feeds.example.org"}), fetcher=fetch)
        self.assertEqual(report["fetched"], 1)
        self.assertEqual(len(report["errors"]), 1)

    def test_html_or_redirect_is_rejected(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status_code = 302
        response.headers = {"Content-Type": "text/html"}
        response.raise_for_status = Mock()
        session = Mock()
        session.get.return_value = response
        with self.assertRaises(ValueError):
            fetch_feed_xml("https://feeds.example.org/rss", allowed_hosts=frozenset({"feeds.example.org"}), resolver=public_dns, session=session)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])

    def test_existing_article_state_not_overwritten(self):
        response = Mock(data=[])
        query = Mock()
        query.upsert.return_value = query
        query.execute.return_value = response
        client = Mock()
        client.table.return_value = query
        saved = upsert_article_metadata(client, FeedSource("id","name","url"), [{"url_hash": "abc"}])
        self.assertEqual(saved, 0)
        self.assertTrue(query.upsert.call_args.kwargs["ignore_duplicates"])

    @patch.dict(os.environ, {}, clear=True)
    def test_worker_requires_explicit_config(self):
        with self.assertRaises(RuntimeError):
            run_worker(dry_run=True)


if __name__ == "__main__":
    unittest.main()
