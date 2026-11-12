# News ingestion worker (PR #6, stacked on PR #5)

## State

- **No feed sources are pre-enabled**: you must obtain authorization for a provider's RSS/API and explicitly register the allowed HTTPS URL in `news_sources`.
- **No cron/deployment is included**. Worker runs only if a person or a separately configured job invokes it.
- **No production Supabase changes**. The PR #5 schema is a review-only file; this worker is not activated on Render.
- News titles, canonical URLs and published times only; **no full-text copying**.
- Ingestion is safe to retry: on-conflict ignore prevents overwriting a previously selected/ignored item.
- Per-source errors are logged as types rather than URLs/credentials; machine-readable report contains counts.

## Prerequisites (staging first)

1. Staging Supabase database with reviewed PR #5 migration applied; validate RLS and permissions.
2. A manually registered news provider with `enabled=true` and `feed_url` HTTPS.
3. Host must be explicitly listed in `NEWS_FEED_HOSTS`.
4. Runner environment (NEVER Next.js client):

```sh
export CONTENT_SUPABASE_URL="https://YOUR-STAGING-PROJECT.supabase.co"
export CONTENT_SUPABASE_PROJECT_ID="YOUR-STAGING-PROJECT"
export CONTENT_SUPABASE_SERVICE_ROLE_KEY="STAGING-SECRET"
export NEWS_FEED_HOSTS="approved-feed.example.org"
```

Dry-run (reads staging source list + performs fetch, but no writes):

```sh
cd backend && python -m content.worker
```

Staging write (explicit opt-in):

```sh
export CONTENT_INGEST_WRITE_ENABLED=yes
cd backend && python -m content.worker --write
```

Keep the secret only in a secure server-side environment, not in git. The
`CONTENT_SUPABASE_PROJECT_ID` guard prevents pointing at a different URL by
accident; before live deployment also use isolated production credentials,
network egress restrictions and a staged release.

## Safety limits

- Explicit feed-domain allowlist and public-IP-only DNS precheck.
- HTTPS only, no ports except 443, no authentication in URL, no redirects.
- Strict 3s connection + 8s read timeout, 2 MiB max response, 50 items/feed,
  20 sources/run. Retry intentionally omitted to avoid hammering providers.
- **DNS rebinding caveat:** DNS may change between validation and connection;
  use an outbound network firewall / proxy allowlist for stronger SSRF defense.
- Validate licensing, robots/rate restrictions and permitted usage for each feed.
- Do not automatically publish articles. An editorial/AI system will be added
  separately, with manual approval as the publication gate.

## Tests

```sh
python -m unittest discover -s backend/tests -v
```
