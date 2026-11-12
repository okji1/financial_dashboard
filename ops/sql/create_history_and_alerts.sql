-- Additive, backend-only storage. Existing token and snapshot policies untouched.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='15s';
CREATE TABLE public.krx_gold_history (
 trade_date date NOT NULL, symbol text NOT NULL CHECK (symbol IN ('04020000','04020100')),
 quote jsonb NOT NULL CHECK (jsonb_typeof(quote)='object'), fetched_at timestamptz NOT NULL,
 PRIMARY KEY(symbol,trade_date)
);
CREATE TABLE public.krx_gold_days (
 trade_date date PRIMARY KEY, fetched_at timestamptz NOT NULL, has_data boolean NOT NULL
);
CREATE TABLE public.dashboard_system_state (
 source text PRIMARY KEY CHECK (source IN ('gold','futures','krx','collector')),
 status text NOT NULL CHECK (status IN ('ok','error')),
 problem_started_at timestamptz, last_snapshot_at timestamptz, checked_at timestamptz NOT NULL
);
CREATE TABLE public.dashboard_system_events (
 id text PRIMARY KEY, source text NOT NULL CHECK (source IN ('gold','futures','krx','collector')),
 status text NOT NULL CHECK (status IN ('error','recovered')), occurred_at timestamptz NOT NULL
);
CREATE INDEX dashboard_system_events_time ON public.dashboard_system_events(occurred_at DESC,id DESC);
ALTER TABLE public.krx_gold_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.krx_gold_days ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dashboard_system_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dashboard_system_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.krx_gold_history,public.krx_gold_days,public.dashboard_system_state,public.dashboard_system_events FROM PUBLIC,anon,authenticated;
GRANT ALL ON public.krx_gold_history,public.krx_gold_days,public.dashboard_system_state,public.dashboard_system_events TO service_role;
CREATE POLICY krx_history_deny_browser ON public.krx_gold_history AS RESTRICTIVE FOR ALL TO anon,authenticated USING(false) WITH CHECK(false);
CREATE POLICY krx_days_deny_browser ON public.krx_gold_days AS RESTRICTIVE FOR ALL TO anon,authenticated USING(false) WITH CHECK(false);
CREATE POLICY system_state_deny_browser ON public.dashboard_system_state AS RESTRICTIVE FOR ALL TO anon,authenticated USING(false) WITH CHECK(false);
CREATE POLICY system_events_deny_browser ON public.dashboard_system_events AS RESTRICTIVE FOR ALL TO anon,authenticated USING(false) WITH CHECK(false);

-- Only the elected collector can record transitions. No public mutation route.
CREATE FUNCTION public.dashboard_record_monitor(p_owner uuid,p_states jsonb)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE lease public.dashboard_collector_lease%ROWTYPE;
 prior public.dashboard_system_state%ROWTYPE;
 item record; observed timestamptz:=clock_timestamp(); snap timestamptz; started timestamptz;
BEGIN
 IF jsonb_typeof(p_states) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'Invalid monitor states'; END IF;
 SELECT * INTO lease FROM public.dashboard_collector_lease WHERE id=true FOR UPDATE;
 IF NOT FOUND OR lease.owner IS DISTINCT FROM p_owner OR lease.expires_at<=observed THEN RETURN false; END IF;
 SELECT collected_at INTO snap FROM public.dashboard_snapshot WHERE id=true;
 FOR item IN SELECT key,value FROM jsonb_each_text(p_states) LOOP
  IF item.key NOT IN ('gold','futures','krx','collector') OR item.value NOT IN ('ok','error') THEN RAISE EXCEPTION 'Invalid monitor state'; END IF;
  SELECT * INTO prior FROM public.dashboard_system_state WHERE source=item.key FOR UPDATE;
  started:=prior.problem_started_at;
  IF item.value='error' AND (prior.source IS NULL OR prior.status='ok') THEN
   started:=CASE WHEN item.key='collector' AND prior.last_snapshot_at IS NOT NULL THEN least(observed,prior.last_snapshot_at+interval '90 seconds') ELSE observed END;
   INSERT INTO public.dashboard_system_events VALUES(item.key||'-error-'||floor(extract(epoch FROM started))::text,item.key,'error',started) ON CONFLICT DO NOTHING;
  ELSIF item.value='ok' AND prior.status='error' THEN
   INSERT INTO public.dashboard_system_events VALUES(item.key||'-recovered-'||floor(extract(epoch FROM observed))::text,item.key,'recovered',observed) ON CONFLICT DO NOTHING;
   started:=NULL;
  ELSIF item.key='collector' AND item.value='ok' AND prior.last_snapshot_at IS NOT NULL AND snap>prior.last_snapshot_at+interval '90 seconds' THEN
   started:=prior.last_snapshot_at+interval '90 seconds';
   INSERT INTO public.dashboard_system_events VALUES('collector-error-'||floor(extract(epoch FROM started))::text,'collector','error',started) ON CONFLICT DO NOTHING;
   INSERT INTO public.dashboard_system_events VALUES('collector-recovered-'||floor(extract(epoch FROM observed))::text,'collector','recovered',observed) ON CONFLICT DO NOTHING;
   started:=NULL;
  END IF;
  INSERT INTO public.dashboard_system_state VALUES(item.key,item.value,started,snap,observed)
  ON CONFLICT(source) DO UPDATE SET status=EXCLUDED.status,problem_started_at=EXCLUDED.problem_started_at,last_snapshot_at=EXCLUDED.last_snapshot_at,checked_at=EXCLUDED.checked_at;
 END LOOP;
 DELETE FROM public.dashboard_system_events WHERE occurred_at<observed-interval '90 days';
 RETURN true;
END;
$$;
REVOKE ALL ON FUNCTION public.dashboard_record_monitor(uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.dashboard_record_monitor(uuid,jsonb) TO service_role;

-- Read models use one round trip and one DB snapshot each. Backend role only.
CREATE FUNCTION public.dashboard_read_krx_history(p_symbol text,p_days integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE today date:=(current_timestamp AT TIME ZONE 'Asia/Seoul')::date;
 items jsonb; checked integer; total integer;
BEGIN
 IF p_symbol NOT IN ('04020000','04020100') OR p_days NOT IN (30,90) OR p_symbol IS NULL OR p_days IS NULL THEN RAISE EXCEPTION 'Invalid history range'; END IF;
 SELECT coalesce(jsonb_agg(q.quote||jsonb_build_object('trade_date',q.trade_date) ORDER BY q.trade_date),'[]'::jsonb) INTO items
 FROM (SELECT trade_date,quote FROM public.krx_gold_history WHERE symbol=p_symbol AND trade_date BETWEEN today-(p_days-1) AND today ORDER BY trade_date LIMIT 366) q;
 SELECT count(d.trade_date)::integer,count(*)::integer INTO checked,total
 FROM generate_series(0,p_days-1) AS g(offset_days)
 LEFT JOIN public.krx_gold_days d ON d.trade_date=today-g.offset_days
 WHERE extract(isodow FROM today-g.offset_days)<6;
 RETURN jsonb_build_object('source','KRX_OPEN_API','symbol',p_symbol,'days',p_days,'items',items,'checked_days',checked,'total_days',total);
END;
$$;
CREATE FUNCTION public.dashboard_read_system_alerts()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT jsonb_build_object(
  'events',(SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY e.occurred_at DESC,e.id DESC),'[]'::jsonb) FROM (SELECT id,source,status,occurred_at FROM public.dashboard_system_events ORDER BY occurred_at DESC,id DESC LIMIT 100) e),
  'collected_at',(SELECT collected_at FROM public.dashboard_snapshot WHERE id=true),
  'collector_status',(SELECT status FROM public.dashboard_system_state WHERE source='collector'));
$$;
REVOKE ALL ON FUNCTION public.dashboard_read_krx_history(text,integer),public.dashboard_read_system_alerts() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.dashboard_read_krx_history(text,integer),public.dashboard_read_system_alerts() TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
