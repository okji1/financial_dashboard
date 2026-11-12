'use client';
import Card from './Card';
import { useMarketData, number, kstTime, ageSeconds } from '../lib/market-data';
import { Badge, Icon, RemoteMessage } from './ui';

export default function ActiveContractManager() {
  const { active, pressure, candidates, requestUpdate, updating, pendingUpdate, updateError, now } = useMarketData();
  const contract = active.data;
  const age = ageSeconds(contract?.updated_at, now);
  const book = pressure.data && pressure.data.symbol === contract?.symbol ? pressure.data : null;
  const fresh = age !== null && age <= 90;
  return <Card title="금선물 계약과 수급" eyebrow="FUTURES DESK" icon="gold" id="futures"
    action={<button className="button button-small" onClick={requestUpdate} disabled={updating || !contract}><Icon name="refresh" className={updating ? 'spinning' : ''}/>{updating ? '요청 중' : '갱신 요청'}</button>}>
    {pendingUpdate && <p className="request-notice" role="status">갱신을 요청했습니다. 최신 결과를 확인하는 중입니다.</p>}
    {updateError && <p className="request-notice warning-text" role="alert">{updateError}</p>}
    {!contract ? <RemoteMessage remote={active} empty="현재 조회 가능한 금선물 계약이 없습니다."/> : <div className="futures-grid">
      <div className="contract-overview"><div className="contract-heading"><span className="contract-symbol">{contract.symbol}</span><Badge tone="gold">활성 계약</Badge></div><p className="muted text-sm">{contract.description}</p>
        <div className="contract-price">{number(contract.current_price)}<span>원</span></div>
        <dl className="contract-facts"><div><dt>누적 거래량</dt><dd>{number(contract.volume)}<small>계약</small></dd></div><div><dt>미결제약정</dt><dd>{number(contract.open_interest)}<small>{contract.open_interest == null ? '미제공' : '계약'}</small></dd></div><div><dt>계약 월</dt><dd>{contract.expiry_year && contract.expiry_month ? `${contract.expiry_year}.${String(contract.expiry_month).padStart(2, '0')}` : '미확인'}</dd></div></dl>
        <div className="source-caption"><Icon name="clock"/>수집 {kstTime(contract.updated_at)} KST{!fresh && <span className="warning-text"> · 시각 재확인 필요</span>}</div>
      </div>
      <div className="pressure-overview"><div className="pressure-heading"><h3>매수·매도 호가 압력</h3><Badge>{book && fresh ? book.pressure_signal : '정보 확인'}</Badge></div>
        {!book || !fresh ? <RemoteMessage remote={pressure} empty="현재 매수·매도 압력 데이터가 없습니다."/> : <>
          <div className="pressure-numbers"><div><span><i className="legend-dot buy-dot"/>매수 잔량 비중</span><strong className="buy-text">{number(book.buy_pressure, 1)}<small>%</small></strong></div><div><span><i className="legend-dot sell-dot"/>매도 잔량 비중</span><strong className="sell-text">{number(book.sell_pressure, 1)}<small>%</small></strong></div></div>
          <div className="pressure-track" role="img" aria-label={`매수 잔량 ${book.buy_pressure}%, 매도 잔량 ${book.sell_pressure}%`}><span style={{ width: `${book.buy_pressure}%` }}/><span style={{ width: `${book.sell_pressure}%` }}/></div>
          <p className="small-note">조회된 호가 잔량의 비율입니다. 실제 체결량이나 가격 상승 확률을 뜻하지 않습니다.</p>
          <div className="source-caption">{book.timestamp.includes('T') ? '호가 응답 수집 시각' : '공급자 호가 시각'} · {book.timestamp.includes('T') ? kstTime(book.timestamp) + ' KST' : book.timestamp} {!book.timestamp.includes('T') && <span>기준일 미제공</span>}</div>
        </>}
      </div>
    </div>}
    <details className="contract-details"><summary><span>계약 후보 <strong>{candidates.data?.count ?? '—'}</strong></span><span className="details-hint">자세히 보기<Icon name="chevron"/></span></summary>
      {candidates.data ? candidates.data.candidates.length ? <div className="candidate-list">{candidates.data.candidates.map(candidate => <div key={candidate.symbol} className={candidate.symbol === contract?.symbol ? 'candidate is-active' : 'candidate'}><span><strong>{candidate.symbol}</strong><small>{candidate.description}</small></span>{candidate.symbol === contract?.symbol ? <Badge tone="gold">활성</Badge> : <span className="muted text-sm">{candidate.year && candidate.month ? `${candidate.year}.${String(candidate.month).padStart(2, '0')}` : '계약 월 미제공'}</span>}</div>)}</div> : <p className="small-note">확인된 금선물 후보가 없습니다.</p> : <RemoteMessage remote={candidates}/>}
      <p className="small-note">한국투자증권의 검증된 상품선물 후보 중 조회된 누적 거래량을 기준으로 선택합니다. 정확한 만기일은 별도 확인이 필요합니다.</p>
    </details>
  </Card>;
}
