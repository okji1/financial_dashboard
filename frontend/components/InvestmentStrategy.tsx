'use client';
import Card from './Card';
import { useMarketData, ageSeconds } from '../lib/market-data';
import { Badge, Icon, RemoteMessage } from './ui';

export default function InvestmentStrategy() {
  const { strategy, premium, now } = useMarketData();
  const age = ageSeconds(premium.data?.timestamp, now);
  const fresh = premium.data && age !== null && age <= 90;
  return <Card title="가격 차이 해석" eyebrow="MARKET INSIGHT" icon="activity" action={<Badge>참고 지표</Badge>}>
    {!strategy.data ? <RemoteMessage remote={strategy}/> : !fresh ? <div className="empty-state"><Icon name="clock"/><p>새로운 시세를 확인한 뒤 해석을 표시합니다.</p><small>오래된 가격으로 새 신호를 표시하지 않습니다.</small></div> : <>
      <div className="insight-grade"><span className="muted text-sm">현재 가격 차이 등급</span><strong>{strategy.data.premium_grade}</strong><span className="insight-caption">가격 차이에 따른 규칙 기반 해석</span></div>
      <div className="signal-list">{strategy.data.signals.map((signal, index) => <div className="signal-item" key={index}><span className="signal-icon"><Icon name="activity"/></span><div><div className="signal-title"><strong>{signal.type}</strong><Badge>{signal.strength}</Badge></div><p>{signal.message}</p></div></div>)}</div>
      <div className="insight-basis"><span className="eyebrow">해석의 기준</span><p>{strategy.data.recommendation}</p></div>
      <p className="small-note">선물·현물 간 가격 차이만으로 계산한 지표입니다. 시세의 시간 차이와 환율 변동을 함께 고려하세요.</p>
    </>}
  </Card>;
}
