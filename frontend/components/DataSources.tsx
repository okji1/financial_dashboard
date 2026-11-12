'use client';
import Card from './Card';
import { Badge, Icon } from './ui';
import { useMarketData, kstTime, ageSeconds } from '../lib/market-data';

export default function DataSources() {
  const { premium, active, pressure, now } = useMarketData();
  const quoteAge = ageSeconds(premium.data?.timestamp, now);
  const futureAge = ageSeconds(active.data?.updated_at, now);
  const quoteState = premium.loading && !premium.data ? '확인 중' : !premium.data ? '확인 실패' : quoteAge !== null && quoteAge <= 90 ? '수집 확인' : '시각 재확인';
  const futureState = active.loading && !active.data ? '확인 중' : active.error?.status === 404 ? '거래 데이터 없음' : !active.data ? '확인 실패' : futureAge !== null && futureAge <= 90 ? '수집 확인' : '시각 재확인';
  const rows = [
    { name: '국내 금 현물', provider: '네이버 금융', symbol: 'M04020000', type: '현물 · 원/g', time: premium.data?.timestamp, state: quoteState, basis: '거래 기준 시각 미제공' },
    { name: '국제 금 선물', provider: '네이버 금융 · COMEX', symbol: 'GCcv1', type: '선물 · 달러/oz', time: premium.data?.timestamp, state: quoteState, basis: '거래 기준 시각 미제공' },
    { name: '원·달러 환율', provider: '한국수출입은행', symbol: 'USD / KRW', type: '기준환율', time: premium.data?.timestamp, state: quoteState, basis: '환율 기준일 미제공' },
    { name: '국내 금선물', provider: '한국투자증권 KIS', symbol: active.data?.symbol ?? '상품선물 마스터', type: '선물 · 시세/호가', time: active.data?.updated_at, state: futureState,
      basis: pressure.data && !pressure.data.timestamp.includes('T') ? `호가 시각 ${pressure.data.timestamp} · 기준일 미제공` : '호가 기준 시각 미제공' },
  ];
  return <Card title="데이터 출처와 기준" eyebrow="DATA TRANSPARENCY" icon="database" id="sources" action={<Badge>한국시간 · KST</Badge>}>
    <div className="source-table"><div className="source-table-head"><span>항목 / 출처</span><span>구분</span><span>수집 시각</span><span>확인 상태</span></div>
      {rows.map(row => <div className="source-row" key={row.name}><div className="source-name"><strong>{row.name}</strong><span>{row.provider}</span><code>{row.symbol}</code></div><div className="source-type"><span>{row.type}</span><small>{row.basis}</small></div><div className="source-time"><span>{kstTime(row.time, true)}</span><small>{row.name === '국내 금선물' ? '계약 수집 시각' : '시세 묶음 수집 시각'}</small></div><Badge tone={row.state === '수집 확인' ? 'positive' : row.state === '확인 실패' ? 'warning' : 'muted'}>{row.state}</Badge></div>)}
    </div>
    <div className="context-note"><Icon name="info"/><p>수집 시각은 공급자의 거래 기준 시각과 다릅니다. 환율은 캐시된 기준환율을 사용할 수 있습니다. 현재 응답에 없는 <strong>장 운영 상태·기준일은 추정해 표시하지 않습니다.</strong></p></div>
  </Card>;
}
