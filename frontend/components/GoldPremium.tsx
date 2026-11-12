'use client';
import Card from './Card';
import { useMarketData, number, ageSeconds, kstTime } from '../lib/market-data';
import { Badge, Icon, RemoteMessage } from './ui';

export default function GoldPremium() {
  const { premium, now } = useMarketData();
  const data = premium.data;
  const age = ageSeconds(data?.timestamp, now);
  const converted = data ? data.london_gold_krw / 31.1035 : 0;
  const maximum = data ? Math.max(converted, data.domestic_gold_price) : 1;
  return <Card title="국내외 가격 비교" eyebrow="PRICE COMPARISON" icon="ratio" action={<Badge>원 / g</Badge>}>
    {!data ? <RemoteMessage remote={premium}/> : <>
      <div className="comparison-summary"><div><span className="muted text-sm">국내 현물과 국제 선물 환산가의 차이</span><div className="comparison-value" data-testid="comparison-premium">{data.premium_percentage > 0 ? '+' : ''}{number(data.premium_percentage, 2)}<span>%</span></div></div><Badge tone="gold">{data.premium_grade}</Badge></div>
      <div className="comparison-row"><div className="comparison-label"><span><i className="legend-dot gold-dot"/>국내 금 현물</span><strong>₩{number(data.domestic_gold_price)}</strong></div><div className="comparison-track"><span className="gold-bar" style={{ width: `${data.domestic_gold_price / maximum * 100}%` }}/></div></div>
      <div className="comparison-row"><div className="comparison-label"><span><i className="legend-dot blue-dot"/>COMEX 금 선물 환산</span><strong>₩{number(converted, 2)}</strong></div><div className="comparison-track"><span className="blue-bar" style={{ width: `${converted / maximum * 100}%` }}/></div></div>
      <div className="context-note"><Icon name="info"/><p>국제 선물과 국내 현물의 <strong>참고 비교</strong>입니다. 같은 시점의 현물 프리미엄이나 실제 체결 가능한 가격 차이를 뜻하지 않습니다.</p></div>
      <div className="panel-meta"><span><Icon name="clock"/>수집 {kstTime(data.timestamp)} KST</span><span className={age !== null && age > 90 ? 'warning-text' : ''}>{age === null ? '수집 시각 확인 중' : age > 90 ? '표시 데이터가 오래되었습니다' : `수집 후 ${age}초`}</span></div>
    </>}
  </Card>;
}
