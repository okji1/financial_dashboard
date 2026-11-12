export class ApiError extends Error {
  constructor(message: string, public status: number = 0) { super(message); }
}

export async function fetchApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  const local = typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname);
  if (!configured && !local) throw new ApiError('API 서버 주소가 설정되지 않았습니다.');
  const base = (configured || 'http://127.0.0.1:5000').replace(/\/$/, '');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(`${base}${path}`, { ...options, signal: controller.signal });
    let result;
    try { result = await response.json(); } catch { throw new ApiError(`서버 응답 형식 오류 (HTTP ${response.status})`, response.status); }
    if (!response.ok || result?.error) {
      const message = response.status === 404 ? '현재 조회 가능한 데이터가 없습니다.'
        : response.status >= 500 ? '데이터 서버 오류입니다. 잠시 후 다시 시도해 주세요.'
        : '요청을 처리할 수 없습니다.';
      throw new ApiError(message, response.status);
    }
    if (!result || typeof result !== 'object') throw new ApiError('서버 응답 형식 오류');
    validatePayload(path.split('?')[0], result);
    return result as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) throw new ApiError('응답 시간이 초과되었습니다. 다시 시도해 주세요.');
    throw new ApiError('서버에 연결할 수 없습니다. 네트워크 또는 접근 설정을 확인해 주세요.');
  } finally { clearTimeout(timer); }
}

function validatePayload(path: string, value: unknown) {
  const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
  const numbers = (v: Record<string, unknown>, fields: string[]) => fields.every(k => typeof v[k] === 'number' && Number.isFinite(v[k]));
  if (!object(value)) throw new ApiError('서버 응답 형식 오류');
  let valid = true;
  if (path === '/api/gold-premium') valid = numbers(value, ['london_gold_usd', 'london_gold_krw', 'domestic_gold_price', 'premium_percentage', 'exchange_rate']) && typeof value.premium_grade === 'string';
  if (path === '/api/investment-strategy') valid = typeof value.premium_grade === 'string' && typeof value.recommendation === 'string' && Array.isArray(value.signals) && value.signals.every(s => object(s) && ['type','message','strength'].every(k => typeof s[k] === 'string'));
  if (path === '/api/gold-analysis') valid = object(value.market_overview) && numbers(value.market_overview, ['london_gold_usd','domestic_gold_price','premium_percentage']) && object(value.risk_assessment) && object(value.risk_assessment.premium_grade) && typeof value.risk_assessment.premium_grade.grade === 'string' && Array.isArray(value.trading_signals) && value.trading_signals.every(s => object(s) && ['type','strength','reason'].every(k => typeof s[k] === 'string')) && Array.isArray(value.recommendations) && value.recommendations.every(r => typeof r === 'string');
  if (path === '/api/futures-candidates') valid = Array.isArray(value.candidates) && value.candidates.every(c => object(c) && typeof c.symbol === 'string');
  if (path === '/api/active-contract') valid = typeof value.symbol === 'string' && numbers(value, ['current_price','volume']);
  if (path === '/api/pressure-signal') valid = typeof value.symbol === 'string' && numbers(value, ['buy_pressure','sell_pressure']) && typeof value.pressure_signal === 'string';
  if (path === '/api/krx-gold-daily') valid = value.source === 'KRX_OPEN_API'
    && typeof value.trade_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value.trade_date)
    && typeof value.fetched_at === 'string' && Number.isFinite(Date.parse(value.fetched_at))
    && ['ok', 'delayed'].includes(String(value.refresh_state))
    && Array.isArray(value.items) && value.items.length > 0 && value.items.every(item => object(item)
      && ['04020000', '04020100'].includes(String(item.symbol)) && typeof item.name === 'string'
      && numbers(item, ['volume_grams', 'trading_value_krw']) && Number(item.volume_grams) >= 0 && Number(item.trading_value_krw) >= 0
      && ['close','change','change_rate','open','high','low'].every(k => item[k] === null || (typeof item[k] === 'number' && Number.isFinite(item[k]))));
  if (path === '/api/krx-gold-history') valid = value.source === 'KRX_OPEN_API'
    && ['04020000','04020100'].includes(String(value.symbol)) && [30,90].includes(Number(value.days))
    && numbers(value,['checked_days','total_days']) && Array.isArray(value.items) && value.items.every(item => object(item)
      && item.symbol === value.symbol && typeof item.trade_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item.trade_date)
      && numbers(item,['volume_grams','trading_value_krw']) && (item.close === null || (typeof item.close === 'number' && Number.isFinite(item.close) && item.close > 0)));
  if (path === '/api/system-alerts') valid = typeof value.checked_at === 'string' && Number.isFinite(Date.parse(value.checked_at))
    && (value.snapshot_age_seconds === null || numbers(value,['snapshot_age_seconds']))
    && Array.isArray(value.events) && value.events.every(item => object(item) && ['id','source','occurred_at','message'].every(k => typeof item[k] === 'string')
      && ['error','recovered'].includes(String(item.status)) && Number.isFinite(Date.parse(String(item.occurred_at))));
  if (!valid) throw new ApiError('서버 응답 데이터 형식이 올바르지 않습니다.');
}
