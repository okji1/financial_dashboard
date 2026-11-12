'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react';
import { ApiError, fetchApi } from './api';

export interface PremiumData {
  london_gold_usd: number; london_gold_krw: number; domestic_gold_price: number;
  premium_percentage: number; premium_grade: string; exchange_rate: number;
  active_contract: string; cached: boolean; timestamp: string;
}
export interface StrategyData {
  premium_grade: string; premium_percentage: number; recommendation: string;
  signals: { type: string; message: string; strength: string }[];
}
export interface AnalysisData {
  timestamp: string;
  market_overview: { london_gold_usd: number; london_gold_krw: number; domestic_gold_price: number; premium_percentage: number };
  risk_assessment: { premium_grade: { grade: string; description: string }; market_volatility: string; liquidity_score: number | null };
  trading_signals: { type: string; strength: string; reason: string }[]; recommendations: string[];
}
export interface Candidate { symbol: string; description: string; year: number | null; month: number | null }
export interface ActiveContract {
  symbol: string; description: string; current_price: number; volume: number; open_interest: number | null;
  expiry_year: number | null; expiry_month: number | null; updated_at: string;
}
export interface PressureData {
  symbol: string; pressure_signal: string; buy_pressure: number; sell_pressure: number;
  recommendation: string; timestamp: string;
}
export interface KRXGoldItem {
  symbol: string; name: string; close: number | null; change: number | null;
  change_rate: number | null; open: number | null; high: number | null; low: number | null;
  volume_grams: number; trading_value_krw: number;
}
export interface KRXGoldDaily {
  source: 'KRX_OPEN_API'; trade_date: string; fetched_at: string;
  refresh_state: 'ok' | 'delayed'; items: KRXGoldItem[];
}
export interface Remote<T> { data: T | null; error: ApiError | null; loading: boolean; checkedAt: number | null }
const initial = <T,>(): Remote<T> => ({ data: null, error: null, loading: true, checkedAt: null });

async function load<T>(path: string, setter: Dispatch<SetStateAction<Remote<T>>>, success?: (value: T) => void) {
  setter(previous => ({ ...previous, loading: true }));
  try {
    const data = await fetchApi<T>(path);
    setter({ data, error: null, loading: false, checkedAt: Date.now() });
    success?.(data);
  } catch (error) {
    setter({ data: null, error: error instanceof ApiError ? error : new ApiError('데이터를 확인할 수 없습니다.'), loading: false, checkedAt: Date.now() });
  }
}

function useMarketController() {
  const [premium, setPremium] = useState<Remote<PremiumData>>(initial);
  const [strategy, setStrategy] = useState<Remote<StrategyData>>(initial);
  const [analysis, setAnalysis] = useState<Remote<AnalysisData>>(initial);
  const [active, setActive] = useState<Remote<ActiveContract>>(initial);
  const [candidates, setCandidates] = useState<Remote<{ candidates: Candidate[]; count: number }>>(initial);
  const [pressure, setPressure] = useState<Remote<PressureData>>(initial);
  const [krx, setKRX] = useState<Remote<KRXGoldDaily>>(initial);
  const [now, setNow] = useState<number | null>(null);
  const [updating, setUpdating] = useState(false);
  const [pendingUpdate, setPendingUpdate] = useState<string | null>(null);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      await Promise.all([
        load('/api/gold-premium', setPremium), load('/api/investment-strategy', setStrategy),
        load('/api/gold-analysis', setAnalysis), load('/api/futures-candidates', setCandidates),
        load('/api/active-contract', setActive, value => setPendingUpdate(previous => previous === value.updated_at ? previous : null)),
        load('/api/pressure-signal', setPressure),
        load('/api/krx-gold-daily', setKRX),
      ]);
    } finally { inFlight.current = false; }
  }, []);
  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const focus = () => { if (document.visibilityState === 'visible') refresh(); };
    document.addEventListener('visibilitychange', focus);
    return () => { clearInterval(interval); clearInterval(tick); document.removeEventListener('visibilitychange', focus); };
  }, [refresh]);

  const requestUpdate = async () => {
    setUpdating(true); setUpdateError(null);
    try {
      const result = await fetchApi<{ contract: ActiveContract; refresh_requested?: boolean }>('/api/update-active-contract', { method: 'POST' });
      setPendingUpdate(result.refresh_requested ? result.contract.updated_at : null);
      await refresh();
    } catch (error) {
      setUpdateError(error instanceof Error ? error.message : '갱신 요청을 처리하지 못했습니다.');
    } finally { setUpdating(false); }
  };
  return { premium, strategy, analysis, active, candidates, pressure, krx, now, refresh, requestUpdate, updating, pendingUpdate, updateError };
}
const Context = createContext<ReturnType<typeof useMarketController> | null>(null);
export function MarketDataProvider({ children }: { children: ReactNode }) {
  const value = useMarketController();
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useMarketData() {
  const value = useContext(Context);
  if (!value) throw new Error('MarketDataProvider is required');
  return value;
}
export function ageSeconds(timestamp: string | undefined, now: number | null) {
  if (!timestamp || now === null) return null;
  const milliseconds = Date.parse(timestamp);
  if (!Number.isFinite(milliseconds) || milliseconds - now > 5000) return null;
  return Math.max(0, Math.floor((now - milliseconds) / 1000));
}
export function kstTime(timestamp?: string | number | null, date = false) {
  if (timestamp === undefined || timestamp === null) return '미제공';
  const parsed = new Date(timestamp);
  if (!Number.isFinite(parsed.getTime())) return '미제공';
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', ...(date ? { month: '2-digit', day: '2-digit' } : {}),
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(parsed);
}
export const number = (value: number | null | undefined, digits = 0) => value == null || !Number.isFinite(value)
  ? '—' : new Intl.NumberFormat('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
