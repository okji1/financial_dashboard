# KIS token cache hardening

The KIS token path is centralized in `kis_auth.get_access_token()`. Both the
futures price and orderbook calls now reuse the same in-process token and
Supabase cache.

- Shared cache lookup fails (DNS/network): **do not issue** a new KIS token.
  Return no token and retry after a cooldown.
- Shared cache has a valid token: reuse it (then use in-process cache).
- No cached token: request one token under a process-level lock.
- Issuance fails: impose a 90-second cooldown rather than retrying for every
  futures candidate.
- Issuance succeeds but persistence fails: reuse token from process memory and
  log an accurate warning.

## Deployment

No new environment variables are required. Existing `KIS_APP_KEY`,
`KIS_APP_SECRET`, `SUPABASE_URL`, and backend-only `SUPABASE_KEY` are needed.

Run offline tests:

```sh
python -m unittest discover -s backend/tests -v
```

## Limitations / further fixes

- The 23-hour memory expiration is based on when the token was first observed,
  not necessarily its true expiration if loaded from an older Supabase row.
  The DB cache still validates its original creation timestamp. For accurate
  expiration across restarts, store the issuer-provided expiration timestamp.
- A thread lock is **not** a distributed lock. Multiple Gunicorn workers or
  Render instances may issue tokens concurrently on expiry. Consider a
  centralized renewal service / distributed lock before scaling.
- A 404 from `/api/pressure-signal` can still occur when no valid gold
  futures contract has nonzero volume; that is not a token problem.
- All four public Supabase tables were reported without RLS, including
  `kis_token`. Before deploying with public client credentials, restrict
  this table to server access; configure and verify RLS policies carefully.
  **This PR does not change database permissions**, to avoid breaking the
  current service unexpectedly.
