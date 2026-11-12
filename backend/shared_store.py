"""Shared, backend-only Supabase snapshots and a server-clock collector lease."""
import datetime
import os
import requests
import copy
import threading
import time

UTC = datetime.timezone.utc
MAX_SECTION_AGE = 90


class StoreUnavailable(RuntimeError):
    pass


class LeaseLost(StoreUnavailable):
    pass


def utc_now():
    return datetime.datetime.now(UTC)


def fresh_timestamp(value, *, max_age=MAX_SECTION_AGE, now=None):
    try:
        parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.tzinfo is not None and 0 <= ((now or utc_now()) - parsed).total_seconds() <= max_age
    except (TypeError, ValueError, AttributeError):
        return False


def section(data=None, state=None):
    return {'state': state or ('ok' if data is not None else 'empty'),
            'data': data, 'collected_at': utc_now().isoformat()}


class SharedStore:
    def __init__(self, url=None, key=None, read_cache_seconds=0):
        self.url = (url or os.getenv('SUPABASE_URL', '')).rstrip('/')
        self.key = key or os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
        self.cache_seconds = max(0, min(float(read_cache_seconds), 15))
        self._cache = None
        self._cache_until = 0.0
        self._cache_lock = threading.Lock()
        self._read_models = {}
        self._read_models_lock = threading.Lock()
        self._read_model_locks = {}
        if not self.url.startswith('https://') or not self.key:
            raise StoreUnavailable('Backend shared-store configuration missing')

    def _request(self, method, path, **kwargs):
        try:
            extra_headers = kwargs.pop('headers', {})
            response = requests.request(method, self.url + '/rest/v1/' + path,
                headers={**extra_headers, 'apikey': self.key, 'Authorization': 'Bearer '+self.key},
                timeout=(3, 8), **kwargs)
            if not response.ok:
                raise StoreUnavailable(f'Shared store HTTP {response.status_code}')
            return response.json()
        except (requests.RequestException, ValueError):
            # Never echo management URLs, response bodies, or request credentials.
            raise StoreUnavailable('Shared store request failed') from None

    def claim(self, owner):
        result = self._request('POST', 'rpc/dashboard_claim_lease', json={'p_owner': owner, 'p_ttl': 60})
        if not isinstance(result, dict) or not result.get('acquired'):
            raise LeaseLost('Another collector owns the lease')
        return result

    def release(self, owner):
        return self._request('POST', 'rpc/dashboard_release_lease', json={'p_owner': owner})

    def publish(self, owner, generation, payload):
        result = self._request('POST', 'rpc/dashboard_publish_snapshot', json={
            'p_owner': owner, 'p_generation': generation, 'p_payload': payload, 'p_ttl': 90})
        if result is not True:
            raise LeaseLost('Collector lost ownership before publication')

    def _validate_row(self, row):
        try:
            expires = datetime.datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00'))
            if expires.tzinfo is None or expires <= utc_now() or not fresh_timestamp(row['collected_at']):
                raise StoreUnavailable('Snapshot expired')
            if not isinstance(row['payload'], dict):
                raise StoreUnavailable('Invalid snapshot payload')
        except (KeyError, TypeError, ValueError):
            raise StoreUnavailable('Invalid snapshot envelope') from None
        return row

    def read(self):
        # Bound egress and merge concurrent dashboard polls without extending expiry.
        with self._cache_lock:
            if self._cache is not None and time.monotonic() < self._cache_until:
                return copy.deepcopy(self._validate_row(self._cache))
            rows = self._request('GET', 'dashboard_snapshot', params={
                'id': 'eq.true', 'select': 'generation,payload,collected_at,expires_at', 'limit': 1})
            if not isinstance(rows, list) or not rows:
                raise StoreUnavailable('Snapshot not yet available')
            row = self._validate_row(rows[0])
            self._cache = copy.deepcopy(row)
            self._cache_until = time.monotonic() + self.cache_seconds
            return row

    def request_refresh(self):
        if self._request('POST', 'rpc/dashboard_request_refresh', json={}) is not True:
            raise StoreUnavailable('Collector not initialized')

    def cached_read(self, key, loader):
        # Small finite keyspace (two products/two ranges + operational inbox).
        with self._read_models_lock:
            key_lock = self._read_model_locks.setdefault(key,threading.Lock())
        with key_lock:
            cached = self._read_models.get(key)
            if cached and time.monotonic() < cached[0]:
                return copy.deepcopy(cached[1])
            value = loader()
            self._read_models[key] = (time.monotonic()+15, copy.deepcopy(value))
            return value

    def token_status(self):
        # Metadata only. Web workers do not read bearer-token values or issue tokens.
        cutoff = (utc_now() - datetime.timedelta(hours=23)).isoformat()
        rows = self._request('GET', 'kis_token', params={'select': 'id',
            'created_at': 'gt.'+cutoff, 'limit': 1})
        return {'cache_hit': bool(rows)}
