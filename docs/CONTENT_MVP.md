# Gold news + editorial AI content — MVP foundation

## Scope of this PR

- **Review-only** SQL schema for four new content tables, with RLS enabled.
- Parser for RSS 2.0 / Atom metadata; canonical URL hashing and deduplication.
- Unit tests; no external traffic, credentials, background jobs or DB writes.
- **No frontend pages, AI provider calls, crawler cron jobs or admin endpoints yet.**
- No existing backend route, Render configuration, Next.js package or historical table is modified.

## Safe operational sequence

1. Review Supabase's current schema and old-table RLS exposure; decide remediation separately.
2. Install Supabase CLI in development and create a real timestamped migration using
   `supabase migration new content_foundation`, then copy and review
   `supabase/schema/content_foundation.review.sql` into the generated migration.
3. Test the migration on an isolated/staging Supabase project. Validate anon cannot
   read drafts/raw feeds or write content; service role can ingest; anonymous visitors
   can read **only** reviewed published posts.
4. Do not apply the migration to production until authorization tests succeed.
5. A subsequent PR implements scheduled fetching (explicit allowlist of legal feed
   sources), bounded network and DNS/SSRF controls, server-side DB upsert and
   auditable ingestion metrics.
6. Another PR implements AI-generated **drafts only**, requiring source verification,
   measured market snapshots, and manual moderator approval before publication.
7. Next.js server-rendered public post pages + sitemap and CMS come afterward.

## Security

The four pre-existing public tables on the linked Supabase project had RLS **disabled**
at the last read, including `kis_token`. This is a serious, **separate production
risk**. Enabling RLS without checking backend credentials can break existing APIs;
review/remediate with a dedicated change and rollback plan.

Do not ship Supabase secret/service role keys or AI API keys to the browser.
Use admin authorization on every publish/edit route and never trust user-controlled
metadata claims as authorization.

## Verify locally

```bash
python -m unittest discover -s backend/tests -v
```

No live external feed fetch or production DB modification is made by these tests.
