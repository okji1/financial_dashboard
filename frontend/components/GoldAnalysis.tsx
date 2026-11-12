'use client';
import Card from './Card';
import { useMarketData, ageSeconds, kstTime } from '../lib/market-data';
import { Badge, RemoteMessage } from './ui';

export default function GoldAnalysis() {
  const { analysis, now } = useMarketData();
  const data = analysis.data;
  const age = ageSeconds(data?.timestamp, now);
  const fresh = age !== null && age <= 90;
  return <Card title="종합 시장 분석" eyebrow="ANALYSIS" icon="layers" id="analysis" action={<Badge>가격 차이 기반</Badge>}>
    {!data ? <RemoteMessage remote={analysis}/> : <>
      <div className="analysis-stats"><div><span>프리미엄 등급</span><strong>{fresh ? data.risk_assessment.premium_grade.grade : '기준 확인 중'}</strong><small>{fresh ? data.risk_assessment.premium_grade.description : '새로운 수집 시세를 기다리고 있습니다'}</small></div><div><span>시장 변동성</span><strong>{data.risk_assessment.market_volatility}</strong><small>시계열 변동성은 현재 제공되지 않습니다</small></div><div><span>유동성 평가</span><strong>{data.risk_assessment.liquidity_score == null ? '미측정' : data.risk_assessment.liquidity_score.toFixed(1)}</strong><small>미제공 항목을 임의 점수로 대체하지 않습니다</small></div></div>
      {fresh ? <div className="analysis-bottom"><div><h3 className="subheading">조건부 매매 지표</h3><div className="trading-signals">{data.trading_signals.map((signal, index) => <div key={index} className="trading-signal"><Badge tone={signal.type === 'HOLD' ? 'muted' : 'gold'}>{signal.type === 'BUY' ? '매수 고려' : signal.type === 'SELL' ? '매도 고려' : '관망'}</Badge><p>{signal.reason}</p><small>신호 강도 · {signal.strength === 'Strong' ? '강함' : signal.strength === 'Medium' ? '중간' : '약함'}</small></div>)}</div></div><div><h3 className="subheading">함께 확인할 사항</h3><ul className="recommendations">{data.recommendations.map((text, index) => <li key={index}>{text}</li>)}</ul></div></div> : <p className="context-note warning-text">새로운 분석 기준 시세를 기다리고 있습니다.</p>}
      <div className="panel-meta"><span>분석 기준 수집 시각</span><span>{kstTime(data.timestamp, true)} KST</span></div>
    </>}
  </Card>;
}
