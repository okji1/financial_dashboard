-- Reviewable migration ONLY; not applied by the preflight command.
-- Prerequisites: inspect current grants/policies; deploy and verify the backend's
-- service_role key; verify its SELECT/INSERT/DELETE access to the required tables.
-- First set the session flag below ONLY after those checks pass:
-- SET dashboard.backend_service_key_verified = 'true';
-- Run in the intended project through a privileged database connection.
-- Retain an external catalog backup of existing grants/policies for rollback.

BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

DO $migration$
DECLARE
    target text;
    policy_record record;
BEGIN
    IF current_setting('dashboard.backend_service_key_verified', true) IS DISTINCT FROM 'true' THEN
        RAISE EXCEPTION 'Deploy and verify the backend service key before enabling RLS';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role' AND rolbypassrls) THEN
        RAISE EXCEPTION 'Expected Supabase service_role with BYPASSRLS';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('anon','authenticated') AND (rolbypassrls OR rolsuper)) THEN
        RAISE EXCEPTION 'Unexpected browser role bypass privilege';
    END IF;
    IF pg_has_role('anon','service_role','MEMBER') OR pg_has_role('authenticated','service_role','MEMBER') THEN
        RAISE EXCEPTION 'Unexpected service_role membership; manual security review required';
    END IF;

    FOREACH target IN ARRAY ARRAY['kis_token','gold_prices','active_contracts','investment_strategies'] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname=target AND c.relkind='r'
        ) THEN
            RAISE EXCEPTION 'Missing expected application table: %', target;
        END IF;
        IF NOT has_table_privilege('service_role', format('public.%I',target), 'SELECT') THEN
            RAISE EXCEPTION 'Backend SELECT grant missing for %', target;
        END IF;
        SELECT * INTO policy_record FROM pg_policies
        WHERE schemaname='public' AND tablename=target AND policyname='dashboard_deny_browser_access';
        IF FOUND THEN
            IF policy_record.permissive IS DISTINCT FROM 'RESTRICTIVE'
               OR policy_record.cmd IS DISTINCT FROM 'ALL'
               OR policy_record.roles IS DISTINCT FROM ARRAY['anon','authenticated']::name[]
               OR policy_record.qual IS DISTINCT FROM 'false'
               OR policy_record.with_check IS DISTINCT FROM 'false' THEN
                RAISE EXCEPTION 'Conflicting existing policy for %; manual review required', target;
            END IF;
        ELSE
            EXECUTE format('CREATE POLICY dashboard_deny_browser_access ON public.%I AS RESTRICTIVE FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)', target);
        END IF;
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', target);
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated', target);
        -- RLS does not protect TRUNCATE; inherited/PUBLIC grants need review.
        IF has_table_privilege('anon', format('public.%I',target), 'TRUNCATE')
           OR has_table_privilege('authenticated', format('public.%I',target), 'TRUNCATE') THEN
            RAISE EXCEPTION 'Inherited browser TRUNCATE privilege on %; manual review required', target;
        END IF;
    END LOOP;
END
$migration$;

COMMIT;

-- Verify AFTER commit through separate real clients:
-- 1. anon and authenticated JWTs: no access to these tables or token values.
-- 2. backend service_role: required application reads/writes still work.
-- 3. /api/token-status returns cache_hit only, and quote/strategy APIs still work.
-- The restrictive policy also denies rows if a public permissive policy remains.
-- No existing policy is deleted. Other tables, auth schema, storage and role
-- membership are untouched. This does NOT rotate old tokens or revoke old keys.
-- Rollback must restore the audited previous grants/RLS/policy state rather than
-- indiscriminately granting privileges or disabling RLS.
