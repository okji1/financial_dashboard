'use client';
import Card from './Card';
import { Badge, Icon, RemoteMessage } from './ui';
import { useMarketData, ageSeconds, kstTime, number } from '../lib/market-data';

export default function KRXGoldDaily() {
  const { krx, now } = useMarketData();
  const data = krx.data;
  const age = ageSeconds(data?.fetched_at, now);
  const delayed = data?.refresh_state === 'delayed' || (age !== null && age > 7200);
  return <Card title="KRX 금시장 일별 거래" eyebrow="OFFICIAL DAILY DATA" icon="database" id="krx" action={<Badge tone={data && !delayed ? 'positive' : 'muted'}>{data ? delayed ? '확인 지연' : '공식 일별 자료' : '연결 확인 중'}</Badge>}>
    {!data ? <RemoteMessage remote={krx} empty="KRX 일별 자료를 확인할 수 없습니다."/> : <>
      <div className="krx-summary"><div><span className="tiny-label">기준 거래일</span><strong data-testid="krx-trade-date">{data.trade_date.replaceAll('-', '. ')}</strong></div><p>한국거래소 OPEN API · 금시장 일별매매정보</p></div>
      {delayed && <div className="context-note krx-warning" role="status"><Icon name="clock"/><p>최신 조회를 확인하지 못했습니다. 마지막으로 수집한 일별 자료와 기준 거래일을 표시합니다.</p></div>}
      <div className="krx-grid">{data.items.map(item => <article className="krx-instrument" key={item.symbol} data-testid={`krx-${item.symbol}`}>
        <div className="krx-instrument-heading"><h3>{item.name}</h3><code>{item.symbol}</code></div>
        <div className="krx-close"><span>{number(item.close)}<small>원 / g</small></span><Badge tone={item.change == null ? 'muted' : item.change > 0 ? 'gold' : item.change < 0 ? 'positive' : 'muted'}>{item.change_rate == null ? '등락률 미제공' : `${item.change_rate > 0 ? '+' : ''}${number(item.change_rate, 2)}%`}</Badge></div>
        <p className="krx-change">종가 · 전일 대비 {item.change == null ? '미제공' : `${item.change > 0 ? '+' : ''}${number(item.change)}원`}</p>
        <dl className="krx-details"><div><dt>시가</dt><dd>{number(item.open)}<small>원/g</small></dd></div><div><dt>고가 / 저가</dt><dd>{number(item.high)} / {number(item.low)}<small>원/g</small></dd></div><div><dt>거래량</dt><dd>{number(item.volume_grams)}<small>g</small></dd></div><div><dt>거래대금</dt><dd>{number(item.trading_value_krw)}<small>원</small></dd></div></dl>
      </article>)}</div>
      <div className="panel-meta"><span><Icon name="clock"/>조회 {kstTime(data.fetched_at, true)} KST</span><span>서버에서 시간당 확인</span></div>
    </>}
    <div className="context-note"><Icon name="info"/><p>실시간 시세가 아닌 <strong>기준 거래일의 일별 자료</strong>입니다. 당일 자료 미제공·휴장 시 최근 14일 내 조회되는 거래일을 표시합니다. 거래량 단위는 g이며 금괴 개수가 아닙니다.</p></div>
  </Card>;
}
