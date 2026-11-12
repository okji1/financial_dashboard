"""Single entry point for KIS access tokens.

Fail closed if the shared Supabase cache cannot be read: an outage must not
trigger a stampede of token issuance requests.
"""
import logging
import threading
import time

from api_utils import get_kis_token
from database import get_cached_token, save_token

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_cached_token = None
_cached_until = 0.0
_retry_after = 0.0
_issuance_guard = None

# Existing database cache uses 23 hours from insertion. Keep in-process
# tokens for at most 23 hours, with a short safety window.
MEMORY_TTL_SECONDS = 23 * 60 * 60 - 60
STORED_TOKEN_RECHECK_SECONDS = 60
FAILED_ISSUE_COOLDOWN_SECONDS = 90


def set_issuance_guard(guard):
    """Collector-only hook. Renew its distributed lease immediately before issuance."""
    global _issuance_guard
    _issuance_guard = guard


def get_access_token():
    """Return a reusable KIS token, or None without spamming the issuer.

    This lock coordinates threads *in one worker*. For multiple processes or
    instances, use a distributed lock / central token-broker at renewal time.
    """
    global _cached_token, _cached_until, _retry_after
    now = time.monotonic()
    if _cached_token and now < _cached_until:
        return _cached_token

    with _lock:
        now = time.monotonic()
        if _cached_token and now < _cached_until:
            return _cached_token
        if now < _retry_after:
            return None

        try:
            token = get_cached_token(strict=True)
        except Exception:
            # Do not equate an inaccessible cache with an expired token.
            logger.warning("KIS shared token cache unavailable; skipping token issuance")
            _retry_after = time.monotonic() + FAILED_ISSUE_COOLDOWN_SECONDS
            return None

        if token:
            _cached_token = token
            _cached_until = time.monotonic() + STORED_TOKEN_RECHECK_SECONDS
            logger.info("Reusing stored KIS access token")
            return token

        if _issuance_guard is not None:
            try:
                _issuance_guard()
            except Exception:
                logger.warning("Collector lease unavailable; skipping token issuance")
                _retry_after = time.monotonic() + FAILED_ISSUE_COOLDOWN_SECONDS
                return None
        try:
            token = get_kis_token()
        except Exception:
            logger.exception("KIS token issue request failed")
            token = None

        if not token:
            logger.warning("KIS token issue failed; cooling down before retry")
            _retry_after = time.monotonic() + FAILED_ISSUE_COOLDOWN_SECONDS
            return None

        # Even if persistence fails, preserve the newly issued token in this
        # worker rather than issuing another one on the next request.
        _cached_token = token
        _cached_until = time.monotonic() + MEMORY_TTL_SECONDS
        try:
            saved = save_token(token)
        except Exception:
            saved = False
        if not saved:
            logger.warning("KIS token issued but shared cache write failed; using memory cache")
        else:
            logger.info("KIS token issued and stored in shared cache")
        return token


def clear_memory_cache():
    """For controlled testing/maintenance; does not revoke KIS credentials."""
    global _cached_token, _cached_until, _retry_after
    with _lock:
        _cached_token = None
        _cached_until = 0.0
        _retry_after = 0.0
