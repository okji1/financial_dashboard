"""Pure RSS/Atom feed normalization for the gold-news content MVP.

No network requests or database writes occur in this module.
Only process feeds from configured, permitted providers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

MAX_FEED_BYTES = 2_000_000
MAX_TITLE_LENGTH = 300
REMOVED_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
ATOM = "{http://www.w3.org/2005/Atom}"


def canonicalize_url(raw: str) -> str:
    """Normalize permitted absolute HTTPS article URLs for deduplication."""
    url = urlsplit((raw or "").strip())
    hostname = url.hostname
    if url.scheme.lower() != "https" or not hostname or url.username or url.password:
        raise ValueError("Only absolute HTTPS article URLs are supported")
    if hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Local hosts are not permitted")
    port = url.port
    netloc = hostname.lower() + (f":{port}" if port and port != 443 else "")
    clean_query = [
        (key, value) for key, value in parse_qsl(url.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in REMOVED_QUERY_KEYS
    ]
    return urlunsplit(("https", netloc, url.path or "/", urlencode(sorted(clean_query)), ""))


def parse_published(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (ValueError, TypeError, IndexError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _text(element: ET.Element, *tags: str) -> str:
    for tag in tags:
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def parse_feed(xml_body: bytes, *, source_id: str, max_items: int = 100) -> list[dict]:
    """Return upsert-ready metadata (no full copyrighted article bodies)."""
    if len(xml_body) > MAX_FEED_BYTES:
        raise ValueError("Feed exceeds size limit")
    if not source_id:
        raise ValueError("source_id required")
    if not 1 <= max_items <= 100:
        raise ValueError("max_items must be 1..100")
    root = ET.fromstring(xml_body)
    rss_items = root.findall("./channel/item")
    is_atom = root.tag == ATOM + "feed"
    if not is_atom and root.tag not in ("rss", "RDF", "{http://purl.org/rss/1.0/}RDF"):
        raise ValueError("Unsupported RSS/Atom document")
    items = root.findall(ATOM + "entry") if is_atom else rss_items
    result: list[dict] = []
    seen: set[str] = set()
    for item in items:
        title = _text(item, ATOM + "title" if is_atom else "title")[:MAX_TITLE_LENGTH]
        raw_url = _text(item, "link")
        if is_atom:
            links = item.findall(ATOM + "link")
            alternate = next((link for link in links if link.get("rel", "alternate") == "alternate" and link.get("href")), None)
            raw_url = alternate.get("href", "") if alternate is not None else ""
        if not title or not raw_url:
            continue
        try:
            url = canonicalize_url(raw_url)
        except ValueError:
            continue
        digest = sha256(url.encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        raw_date = _text(item, ATOM + "published", ATOM + "updated") if is_atom else _text(item, "pubDate", "{http://purl.org/dc/elements/1.1/}date")
        result.append({
            "source_id": source_id,
            "title": title,
            "original_url": url,
            "url_hash": digest,
            "published_at": parse_published(raw_date),
            "category": "general",
            "status": "collected",
            "metadata": {},
        })
        if len(result) >= max_items:
            break
    return result
