-- REVIEW-ONLY SQL. Do NOT apply to production without a staging DB test.
-- Make a timestamped migration with 'supabase migration new content_foundation'
-- when the Supabase CLI is available, and copy this reviewed SQL into it.
-- This file does not modify any existing table.
create extension if not exists pgcrypto;

create table public.news_sources (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  feed_url text not null unique check (feed_url ~ '^https://'),
  source_type text not null check (source_type in ('rss','atom','api')),
  enabled boolean not null default false,
  last_fetched_at timestamptz,
  created_at timestamptz not null default now()
);

create table public.news_articles (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.news_sources(id) on delete restrict,
  title text not null,
  original_url text not null check (original_url ~ '^https://'),
  url_hash text not null unique,
  published_at timestamptz,
  category text not null default 'general',
  status text not null default 'collected'
    check (status in ('collected','selected','ignored')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.content_posts (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  title text not null,
  description text,
  body_md text not null default '',
  seo_title text,
  seo_description text,
  status text not null default 'draft'
    check (status in ('draft','review','published','rejected')),
  category text not null default 'market-analysis',
  market_snapshot jsonb not null default '{}'::jsonb,
  reviewed_at timestamptz,
  published_at timestamptz,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  constraint published_requires_review check (
    status <> 'published'
    or (published_at is not null and reviewed_at is not null)
  )
);

create table public.content_sources (
  post_id uuid not null references public.content_posts(id) on delete cascade,
  article_id uuid references public.news_articles(id) on delete set null,
  source_url text not null check (source_url ~ '^https://'),
  source_title text,
  primary key (post_id, source_url)
);

create index news_articles_published_idx
  on public.news_articles (published_at desc);
create index news_articles_source_idx
  on public.news_articles (source_id, created_at desc);
create index content_posts_published_idx
  on public.content_posts (published_at desc) where status = 'published';
create index content_posts_review_idx
  on public.content_posts (status, created_at desc);

-- Restrict access before any public role can read drafts or raw metadata.
alter table public.news_sources enable row level security;
alter table public.news_articles enable row level security;
alter table public.content_posts enable row level security;
alter table public.content_sources enable row level security;

revoke all on table
  public.news_sources, public.news_articles,
  public.content_posts, public.content_sources
  from public, anon, authenticated;

-- Backend-only credentials (never NEXT_PUBLIC_*).
grant select, insert, update, delete on table
  public.news_sources, public.news_articles,
  public.content_posts, public.content_sources
  to service_role;

-- The only public read surface: manually reviewed, published articles.
grant select on table public.content_posts to anon, authenticated;
create policy content_posts_published_read
  on public.content_posts for select to anon, authenticated
  using (status = 'published' and published_at <= now());

-- No client write policies are created. Approval and publishing MUST
-- go through an authenticated, server-only administrative endpoint.
