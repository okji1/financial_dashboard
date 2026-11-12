'use client';
import { useEffect, useRef, useState } from 'react';
import Card from './Card';
import { Badge, Icon, RemoteMessage } from './ui';
import { ApiError, fetchApi } from '../lib/api';
import { number, type KRXHistory, type Remote } from '../lib/market-data';

export default function KRXHistoryChart() {
  const [symbol,setSymbol] = useState('04020000');
  const [days,setDays] = useState(90);
  const [remote,setRemote] = useState<Remote<KRXHistory>>({data:null,error:null,loading:true,checkedAt:null});
  const [selected,setSelected] = useState<number | null>(null);
  const plot=useRef<HTMLDivElement>(null);
  const [plotWidth,setPlotWidth]=useState(900);
  useEffect(() => {
    let cancelled=false;
    const load=async () => {
      setRemote(previous=>({...previous,loading:true}));
      try {
        const data=await fetchApi<KRXHistory>(`/api/krx-gold-history?symbol=${symbol}&days=${days}`);
        if (!cancelled) { setRemote({data,error:null,loading:false,checkedAt:Date.now()}); setSelected(null); }
      } catch(error) {
        if (!cancelled) setRemote({data:null,error:error instanceof ApiError ? error : new ApiError('이력을 조회하지 못했습니다.'),loading:false,checkedAt:Date.now()});
      }
    };
    load(); const timer=setInterval(load,300000);
    return()=>{cancelled=true;clearInterval(timer);};
  },[symbol,days]);
  // Hide the previous product/range while the new selection is being loaded.
  const data=remote.data?.symbol === symbol && remote.data.days === days ? remote.data : null;
  const rows=data?.items || [];
  useEffect(()=>{
    if(!plot.current)return;
    const observer=new ResizeObserver(entries=>setPlotWidth(Math.max(300,Math.min(900,Math.floor(entries[0].contentRect.width)))));
    observer.observe(plot.current);return()=>observer.disconnect();
  },[data?.symbol,data?.days,rows.length]);
  const valid=rows.filter(row=>row.close !== null);
  const prices=valid.map(row=>row.close!);
  const low=prices.length ? Math.min(...prices) : 0, high=prices.length ? Math.max(...prices) : 1;
  const padding=Math.max((high-low)*.15,high*.002,1);
  const min=low-padding,max=high+padding;
  const span=plotWidth-85;
  const x=(i:number)=>65+(rows.length>1 ? i/(rows.length-1)*span : span/2);
  const y=(price:number)=>25+(max-price)/(max-min)*215;
  let drawing=false;
  const path=rows.map((row,i)=>{if(row.close === null){drawing=false;return '';}const command=drawing?'L':'M';drawing=true;return `${command}${x(i)},${y(row.close)}`;}).join(' ');
  const maxVolume=Math.max(1,...rows.map(row=>row.volume_grams));
  const index=rows.length ? Math.min(selected ?? rows.length-1, rows.length-1) : 0;
  const focused=rows[index];
  const first=valid[0]?.close, last=valid[valid.length-1]?.close;
  const change=valid.length>1 && first && last ? (last-first)/first*100 : null;
  return <Card title="KRX 금 가격 추이" eyebrow="MARKET HISTORY" icon="activity" id="history" action={<Badge>{rows.length}개 거래일</Badge>}>
    <div className="history-toolbar"><div className="segmented" role="group" aria-label="차트 상품"><button aria-pressed={symbol==='04020000'} onClick={()=>setSymbol('04020000')}>금 1kg</button><button aria-pressed={symbol==='04020100'} onClick={()=>setSymbol('04020100')}>미니금 100g</button></div><div className="segmented" role="group" aria-label="차트 기간">{[30,90].map(d=><button key={d} aria-pressed={days===d} onClick={()=>setDays(d)}>{d}일</button>)}</div></div>
    {!data ? <RemoteMessage remote={remote} empty="아직 저장된 KRX 이력이 없습니다."/> : !rows.length ? <div className="empty-state"><Icon name="layers"/><p>저장된 거래일이 없습니다. 수집된 자료부터 표시됩니다.</p></div> : <>
      <div className="chart-stat"><div><span>선택 기간 종가 변화</span><strong data-testid="history-change">{change == null ? '—' : `${change>0?'+':''}${number(change,2)}%`}</strong></div><p>{rows[0].trade_date} — {rows[rows.length-1].trade_date}</p></div>
      <div className="chart-selection" aria-live="polite" data-testid="history-selection"><strong>{focused.trade_date}</strong><span>종가 {number(focused.close)} 원/g</span><span>거래량 {number(focused.volume_grams)} g</span></div>
      <div className="history-plot" ref={plot}><svg viewBox={`0 0 ${plotWidth} 340`} role="img" aria-label={`${symbol==='04020000'?'금 1kg':'미니금 100g'} ${days}일 종가와 거래량 차트`} onPointerMove={event=>{const rect=event.currentTarget.getBoundingClientRect();const pos=(event.clientX-rect.left)/rect.width*plotWidth;setSelected(Math.max(0,Math.min(rows.length-1,Math.round((pos-65)/span*(rows.length-1)))));}} onPointerLeave={()=>setSelected(null)}>
        {valid.length>0 ? [0,.5,1].map(t=><g key={t}><line x1="65" x2={plotWidth-20} y1={25+t*215} y2={25+t*215} className="chart-grid"/><text x="55" y={29+t*215} textAnchor="end" className="chart-axis">{number(max-t*(max-min))}</text></g>) : <text x={plotWidth/2} y="130" textAnchor="middle" className="chart-axis">종가 미제공</text>}
        <text x="65" y="13" className="chart-axis">종가 · 원/g</text>
        <path d={path} className="chart-price"/>
        {rows.map((row,i)=>row.close!==null && (i===0||rows[i-1].close===null) && (i===rows.length-1||rows[i+1].close===null) ? <circle key={row.trade_date} cx={x(i)} cy={y(row.close)} r="3" className="chart-point"/> : null)}
        <text x="65" y="268" className="chart-axis">거래량 · g</text>
        {rows.map((row,i)=><rect key={row.trade_date} x={x(i)-Math.min(6,span*.38/rows.length)} y={318-row.volume_grams/maxVolume*38} width={Math.max(1,Math.min(12,span*.76/rows.length))} height={row.volume_grams/maxVolume*38} className="chart-volume"/>)}
        <line x1={x(index)} x2={x(index)} y1="25" y2="318" className="chart-guide"/>
        {focused.close !== null && <circle cx={x(index)} cy={y(focused.close)} r="4" className="chart-point"/>}
        <text x="65" y="337" className="chart-axis">{rows[0].trade_date.slice(5)}</text><text x={plotWidth-20} y="337" textAnchor="end" className="chart-axis">{rows[rows.length-1].trade_date.slice(5)}</text>
      </svg></div>
      <label className="chart-slider">날짜 탐색<input type="range" min="0" max={Math.max(0,rows.length-1)} value={index} onChange={e=>setSelected(Number(e.target.value))} aria-label="차트 거래일 탐색" aria-valuetext={`${focused.trade_date} 종가 ${number(focused.close)}원 거래량 ${number(focused.volume_grams)}그램`}/></label>
      <div className="panel-meta"><span>{data.checked_days}/{data.total_days}개 평일 조회 완료</span><span>{data.checked_days<data.total_days?'이력 수집 중 · 저장된 자료만 표시':'요청 기간 조회 완료'}</span></div>
      <details className="history-table-details"><summary>거래일별 원자료 보기</summary><div className="history-table-scroll"><table><caption className="sr-only">KRX 거래일별 종가와 거래량</caption><thead><tr><th>거래일</th><th>종가 (원/g)</th><th>거래량 (g)</th></tr></thead><tbody>{rows.map(row=><tr key={row.trade_date}><td>{row.trade_date}</td><td>{number(row.close)}</td><td>{number(row.volume_grams)}</td></tr>)}</tbody></table></div></details>
    </>}
    <div className="context-note"><Icon name="info"/><p>KRX 공식 일별 자료를 저장한 차트입니다. 휴장일은 제외하고 제공되지 않은 종가는 선을 끊어 표시합니다. 가격 변화는 저장된 첫 종가와 마지막 종가의 비교입니다.</p></div>
  </Card>;
}
