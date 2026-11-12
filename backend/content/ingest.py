"""Explicitly invoked RSS/Atom ingestion; no background jobs or live DB default.

Network source protection:
- feed host must be explicitly allowlisted
- DNS must resolve only to globally routable IP addresses
- HTTPS only, no redirect, strict connect/read timeout and response byte cap
- egress firewall / private DNS restriction is still recommended: DNS rebinding
  between validation and TCP connect is not solved by application checks alone.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import logging
import os
import socket
from urllib.parse import urlsplit

import requests

from content.feed_parser import MAX_FEED_BYTES, parse_feed

log = logging.getLogger(__name__)
TIMEOUT = (3, 8)
MAX_SOURCES = 20
MAX_ITEMS_PER_SOURCE = 50


@dataclass(frozen=True)
class FeedSource:
    id: str
    name: str
    feed_url: str


def allowed_hosts_from_env() -> frozenset[str]:
    return frozenset(s.strip().lower() for s in os.getenv("NEWS_FEED_HOSTS", "").split(",") if s.strip())


def validate_feed_url(url: str, *, allowed_hosts: frozenset[str], resolver=socket.getaddrinfo) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Feed must use canonical HTTPS URL without credentials, fragment or custom port")
    host = parsed.hostname.lower().rstrip(".")
    if host not in allowed_hosts:
        raise ValueError("Feed host is not in NEWS_FEED_HOSTS")
    try:
        records = resolver(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Feed host DNS lookup failed") from exc
    if not records:
        raise ValueError("Feed host has no DNS records")
    for record in records:
        address = ipaddress.ip_address(record[4][0])
        if not address.is_global:
            raise ValueError("Feed host resolves to a non-public IP")
    return host


def fetch_feed_xml(
    url: str,
    *,
    allowed_hosts: frozenset[str],
    resolver=socket.getaddrinfo,
    session=None,
) -> bytes:
    validate_feed_url(url, allowed_hosts=allowed_hosts, resolver=resolver)
    client = session or requests
    with client.get(
        url,
        stream=True,
        timeout=TIMEOUT,
        allow_redirects=False,
        headers={"User-Agent": "FinancialDashboardNewsBot/0.1 (+contact-site-owner)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"},
    ) as response:
        response.raise_for_status()
        if 300 <= response.status_code < 400:
            raise ValueError("Feed redirects are not permitted")
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
        if content_type not in {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}:
            raise ValueError("Unexpected feed content-type")
        data = bytearray()
        for chunk in response.iter_content(chunk_size=16_384):
            data.extend(chunk)
            if len(data) > MAX_FEED_BYTES:
                raise ValueError("Feed exceeds maximum byte size")
        return bytes(data)


def ingest_sources(
    sources: list[FeedSource],
    *,
    allowed_hosts: frozenset[str],
    fetcher=fetch_feed_xml,
    sink=None,
    dry_run=True,
) -> dict:
    """Ingest one page per enabled source.

    sink(source, articles) is called only with collected metadata and only
    with dry_run=False. Exceptions are recorded, without leaking credentials.
    """
    if len(sources) > MAX_SOURCES:
        raise ValueError("Too many sources for one run")
    if not dry_run and sink is None:
        raise ValueError("A persistence sink is required when dry_run=False")
    result = {"sources": len(sources), "fetched": 0, "items": 0, "saved": 0, "errors": []}
    for source in sources:
        try:
            body = fetcher(source.feed_url, allowed_hosts=allowed_hosts)
            rows = parse_feed(body, source_id=source.id, max_items=MAX_ITEMS_PER_SOURCE)
            result["fetched"] += 1
            result["items"] += len(rows)
            if not dry_run and rows:
                result["saved"] += int(sink(source, rows))
        except (requests.RequestException, ValueError, OSError) as exc:
            log.warning("Source %s ingestion failed: %s", source.id, type(exc).__name__)
            result["errors"].append({"source_id": source.id, "error_type": type(exc).__name__})
    return result
