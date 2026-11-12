-- Additive migration. Does not alter existing application tables or token data.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='15s';

CREATE TABLE public.dashboard_snapshot (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    generation uuid NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object'),
    collected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL
);
CREATE TABLE public.dashboard_collector_lease (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    owner uuid NOT NULL,
    expires_at timestamptz NOT NULL,
    refresh_requested_at timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00Z'
);
ALTER TABLE public.dashboard_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dashboard_collector_lease ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.dashboard_snapshot,public.dashboard_collector_lease FROM PUBLIC,anon,authenticated;
GRANT ALL ON public.dashboard_snapshot,public.dashboard_collector_lease TO service_role;
CREATE POLICY dashboard_snapshot_deny_browser ON public.dashboard_snapshot AS RESTRICTIVE FOR ALL TO anon,authenticated USING(false) WITH CHECK(false);
CREATE POLICY dashboard_lease_deny_browser ON public.dashboard_collector_lease AS RESTRICTIVE FOR ALL TO anon,authenticated USING(false) WITH CHECK(false);

CREATE FUNCTION public.dashboard_claim_lease(p_owner uuid,p_ttl integer DEFAULT 60)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE current_lease public.dashboard_collector_lease%ROWTYPE;
BEGIN
    IF p_owner IS NULL OR p_ttl NOT BETWEEN 30 AND 180 THEN RAISE EXCEPTION 'Invalid lease request'; END IF;
    INSERT INTO public.dashboard_collector_lease AS lease(id,owner,expires_at)
    VALUES(true,p_owner,clock_timestamp()+make_interval(secs=>p_ttl))
    ON CONFLICT(id) DO UPDATE SET owner=EXCLUDED.owner,expires_at=EXCLUDED.expires_at
    WHERE lease.owner=p_owner OR lease.expires_at<=clock_timestamp()
    RETURNING lease.* INTO current_lease;
    IF NOT FOUND THEN
        SELECT * INTO current_lease FROM public.dashboard_collector_lease WHERE id=true;
    END IF;
    RETURN jsonb_build_object('acquired',current_lease.owner=p_owner AND current_lease.expires_at>clock_timestamp(),
        'refresh_requested_at',current_lease.refresh_requested_at);
END;
$$;

CREATE FUNCTION public.dashboard_publish_snapshot(p_owner uuid,p_generation uuid,p_payload jsonb,p_ttl integer DEFAULT 90)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE current_lease public.dashboard_collector_lease%ROWTYPE;
BEGIN
    IF p_ttl NOT BETWEEN 30 AND 120 OR p_generation IS NULL OR p_payload IS NULL
       OR jsonb_typeof(p_payload)<>'object' OR octet_length(p_payload::text)>1048576 THEN
        RAISE EXCEPTION 'Invalid snapshot';
    END IF;
    SELECT * INTO current_lease FROM public.dashboard_collector_lease WHERE id=true FOR UPDATE;
    IF NOT FOUND OR current_lease.owner IS DISTINCT FROM p_owner OR current_lease.expires_at<=clock_timestamp() THEN
        RETURN false;
    END IF;
    INSERT INTO public.dashboard_snapshot(id,generation,payload,collected_at,expires_at)
    VALUES(true,p_generation,p_payload,clock_timestamp(),clock_timestamp()+make_interval(secs=>p_ttl))
    ON CONFLICT(id) DO UPDATE SET generation=EXCLUDED.generation,payload=EXCLUDED.payload,
        collected_at=EXCLUDED.collected_at,expires_at=EXCLUDED.expires_at;
    RETURN true;
END;
$$;

CREATE FUNCTION public.dashboard_request_refresh()
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
    UPDATE public.dashboard_collector_lease SET refresh_requested_at=clock_timestamp() WHERE id=true;
    RETURN FOUND;
END;
$$;

CREATE FUNCTION public.dashboard_release_lease(p_owner uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
    UPDATE public.dashboard_collector_lease SET expires_at=clock_timestamp() WHERE id=true AND owner=p_owner;
    RETURN FOUND;
END;
$$;

REVOKE ALL ON FUNCTION public.dashboard_claim_lease(uuid,integer),
 public.dashboard_publish_snapshot(uuid,uuid,jsonb,integer),public.dashboard_request_refresh(),
 public.dashboard_release_lease(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.dashboard_claim_lease(uuid,integer),
 public.dashboard_publish_snapshot(uuid,uuid,jsonb,integer),public.dashboard_request_refresh(),
 public.dashboard_release_lease(uuid) TO service_role;
NOTIFY pgrst, 'reload schema';
COMMIT;
