"""Offline, no-network checks for RSS/Atom normalization."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content.feed_parser import canonicalize_url, parse_feed, parse_published


RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Example</title>
<item><title>Gold outlook</title><link>https://news.example.com/gold?utm_source=foo&amp;x=1</link><pubDate>Thu, 12 Nov 2026 04:00:00 GMT</pubDate></item>
<item><title>Duplicate</title><link>https://news.example.com/gold?x=1&amp;utm_medium=bar</link></item>
<item><title>Unsafe</title><link>http://news.example.com/unsafe</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Gold analysis</title>
  <link rel="alternate" href="https://news.example.com/article"/>
  <updated>2026-11-12T04:00:00Z</updated></entry>
</feed>"""


class FeedParserTests(unittest.TestCase):
    def test_canonicalizes_tracking_parameters_and_fragment(self):
        self.assertEqual(
            canonicalize_url("https://NEWS.example.com/gold?utm_source=x&b=2&a=1#top"),
            "https://news.example.com/gold?a=1&b=2",
        )

    def test_invalid_or_local_urls_rejected(self):
        for value in ("http://example.org", "https://localhost/", "javascript:alert(1)", "https://x:y@example.org/"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonicalize_url(value)

    def test_rss_deduplicates_and_never_stores_article_body(self):
        items = parse_feed(RSS, source_id="source-1")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Gold outlook")
        self.assertEqual(items[0]["original_url"], "https://news.example.com/gold?x=1")
        self.assertNotIn("body", items[0])
        self.assertEqual(items[0]["published_at"], "2026-11-12T04:00:00+00:00")

    def test_atom_link_and_date(self):
        items = parse_feed(ATOM, source_id="source-2")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["original_url"], "https://news.example.com/article")
        self.assertEqual(items[0]["published_at"], "2026-11-12T04:00:00+00:00")

    def test_rejects_oversized_or_invalid_feeds(self):
        with self.assertRaises(ValueError):
            parse_feed(b"x" * 2_000_001, source_id="test")
        with self.assertRaises(ValueError):
            parse_feed(b"<hello/>", source_id="test")

    def test_missing_date(self):
        self.assertIsNone(parse_published("not a date"))

    def test_invalid_max_items(self):
        with self.assertRaises(ValueError):
            parse_feed(RSS, source_id="test", max_items=0)


if __name__ == "__main__":
    unittest.main()
