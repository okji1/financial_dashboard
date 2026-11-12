'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import Card from './Card';
import { Badge, Icon } from './ui';
import { useMarketData, kstTime } from '../lib/market-data';
import { ALERT_STORAGE_KEY, emptyAlerts, restoreAlerts, evaluateRules, addEvents, ruleLabel, type AlertState, type AlertRule, type Metric } from '../lib/alerts';

export default function AlertCenter({ onUnreadChange }: { onUnreadChange?: (count:number)=>void }) {
  const {premium,systemAlerts,now}=useMarketData();
  const [state,setState]=useState<AlertState>(emptyAlerts);
  const [ready,setReady]=useState(false);
  const [storageError,setStorageError]=useState(false);
  const [metric,setMetric]=useState<Metric>('price');
  const [operator,setOperator]=useState<'gte'|'lte'>('gte');
  const [threshold,setThreshold]=useState('180000');
  const [formError,setFormError]=useState('');
  const [filter,setFilter]=useState<'all'|'unread'|'condition'|'system'>('all');
  const failedSince=useRef<number|null>(null);
  const failureNotified=useRef(false);
  useEffect(()=>{
    try{setState(restoreAlerts(localStorage.getItem(ALERT_STORAGE_KEY)));}catch{setStorageError(true);}
    setReady(true);
    const sync=(event:StorageEvent)=>{if(event.key===ALERT_STORAGE_KEY)setState(restoreAlerts(event.newValue));};
    window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync);
  },[]);
  useEffect(()=>{
    if(!ready)return;
    try{localStorage.setItem(ALERT_STORAGE_KEY,JSON.stringify(state));}catch{setStorageError(true);}
  },[state,ready]);
  useEffect(()=>{
    if(!ready||now===null||premium.loading)return;
    setState(previous=>evaluateRules(previous,premium.data,now));
  },[premium.data,premium.loading,now,ready]);
  // A newly added/enabled rule is evaluated immediately against a fresh quote.
  const applyRules=(rules:AlertRule[])=>setState(previous=>{
    const next={...previous,rules};return now===null?next:evaluateRules(next,premium.loading?null:premium.data,now);
  });
  useEffect(()=>{
    if(!ready||!systemAlerts.data)return;
    setState(previous=>addEvents(previous,systemAlerts.data!.events.map(event=>({id:'system:'+event.id,kind:'system',severity:event.status==='recovered'?'recovery':'warning',occurred_at:event.occurred_at,message:event.message}))));
  },[systemAlerts.data,ready]);
  useEffect(()=>{
    if(!ready||now===null||systemAlerts.loading)return;
    if(systemAlerts.error){
      if(failedSince.current===null)failedSince.current=now;
      if(now-failedSince.current>=30000&&!failureNotified.current){
        failureNotified.current=true;
        setState(previous=>addEvents(previous,[{id:`connection:${failedSince.current}`,kind:'system',severity:'warning',occurred_at:new Date(now).toISOString(),message:'서버 알림 상태를 30초 이상 확인하지 못했습니다. API 연결이나 서비스 상태를 확인하세요.'}]));
      }
    }else if(systemAlerts.data&&failedSince.current!==null){
      if(failureNotified.current)setState(previous=>addEvents(previous,[{id:`connection-recovered:${failedSince.current}`,kind:'system',severity:'recovery',occurred_at:new Date(now).toISOString(),message:'서버 알림 상태 조회가 정상으로 복구됐습니다.'}]));
      failedSince.current=null;failureNotified.current=false;
    }
  },[ready,now,systemAlerts.loading,systemAlerts.error,systemAlerts.data]);
  const addRule=(event:FormEvent)=>{
    event.preventDefault();const value=Number(threshold);
    if(!threshold.trim()||!Number.isFinite(value)||(metric==='price'&&value<=0)||Math.abs(value)>1e9){setFormError('유효한 기준값을 입력하세요. 금 가격은 0보다 커야 합니다.');return;}
    if(state.rules.length>=10){setFormError('조건은 최대 10개까지 등록할 수 있습니다.');return;}
    if(state.rules.some(r=>r.metric===metric&&r.operator===operator&&r.threshold===value)){setFormError('같은 조건이 이미 등록돼 있습니다.');return;}
    const rule:AlertRule={id:crypto.randomUUID(),metric,operator,threshold:value,enabled:true,matched:false,lastFiredAt:null};
    applyRules([...state.rules,rule]);setFormError('');
  };
  const read=new Set(state.readIds);
  const unread=state.events.filter(event=>!read.has(event.id)).length;
  useEffect(()=>{onUnreadChange?.(unread);},[unread,onUnreadChange]);
  const events=state.events.filter(event=>filter==='all'||filter==='unread'&&!read.has(event.id)||filter===event.kind);
  const markRead=(id:string)=>setState(previous=>({...previous,readIds:Array.from(new Set([...previous.readIds,id])).slice(-200)}));
  return <Card title="알림함과 조건 설정" eyebrow="ALERT CENTER" icon="bell" id="alerts" action={<Badge tone={unread?'gold':'muted'}>읽지 않음 {unread}</Badge>}>
    {!ready?<p className="empty-state">이 브라우저의 설정을 불러오고 있습니다.</p>:<>
      <div className="alerts-intro"><div><h3>나의 가격 알림</h3><p>새 시세가 조건에 진입할 때 알림함에 기록합니다.</p></div><Badge>{state.rules.filter(r=>r.enabled).length}개 사용 중</Badge></div>
      <form className="alert-form" onSubmit={addRule}>
        <label>대상<select aria-label="알림 대상" value={metric} onChange={e=>{setMetric(e.target.value as Metric);setThreshold(e.target.value==='price'?'180000':'2');}}><option value="price">국내 금 현물 (원/g)</option><option value="premium">국내외 가격 차이 (%)</option></select></label>
        <label>기준값<input aria-label="알림 기준값" type="number" step="any" value={threshold} onChange={e=>setThreshold(e.target.value)} required/></label>
        <label>조건<select aria-label="알림 비교 조건" value={operator} onChange={e=>setOperator(e.target.value as 'gte'|'lte')}><option value="gte">이상</option><option value="lte">이하</option></select></label>
        <button className="button button-primary" type="submit">조건 추가<Icon name="bell"/></button>
      </form>
      {formError&&<p className="form-error" role="alert">{formError}</p>}
      <div className="alert-rules">{state.rules.length===0?<p className="muted-note">등록된 조건이 없습니다. 원하는 가격 또는 가격 차이 기준을 추가하세요.</p>:state.rules.map(rule=><div className="alert-rule" key={rule.id}><div><strong>{ruleLabel(rule)}</strong><small>{rule.enabled?rule.matched?'조건 충족 · 재진입 대기':'새 시세 확인 중':'일시 중지'}</small></div><div className="alert-rule-actions"><button className="text-button" aria-label={`${ruleLabel(rule)} ${rule.enabled?'중지':'사용'}`} aria-pressed={rule.enabled} onClick={()=>applyRules(state.rules.map(r=>r.id===rule.id?{...r,enabled:!r.enabled,matched:false}:r))}>{rule.enabled?'중지':'사용'}</button><button className="text-button" aria-label={`${ruleLabel(rule)} 삭제`} onClick={()=>applyRules(state.rules.filter(r=>r.id!==rule.id))}>삭제</button></div></div>)}</div>
      <div className="alerts-inbox-toolbar"><div className="segmented" role="group" aria-label="알림 필터">{(['all','unread','condition','system'] as const).map(value=><button key={value} aria-pressed={filter===value} onClick={()=>setFilter(value)}>{({all:'전체',unread:'안 읽음',condition:'가격 조건',system:'수집 상태'})[value]}</button>)}</div><button className="text-button" onClick={()=>setState(previous=>({...previous,readIds:previous.events.map(e=>e.id)}))} disabled={!unread}>모두 읽음</button></div>
      {systemAlerts.error&&<p className="muted-note" role="status">서버 알림 상태를 조회하지 못했습니다. 마지막으로 저장된 알림을 표시합니다.</p>}
      <div className="inbox-list" aria-label="알림 목록" aria-live="polite">{events.length===0?<div className="empty-state"><Icon name="bell"/><p>{filter==='unread'?'읽지 않은 알림이 없습니다.':'표시할 알림이 없습니다.'}</p></div>:events.map(event=><article key={event.id} className={`inbox-event ${read.has(event.id)?'is-read':'is-unread'}`} data-testid="inbox-event"><span className={`inbox-icon ${event.severity}`}><Icon name={event.severity==='recovery'?'activity':'bell'}/></span><div><span className="inbox-event-type">{event.kind==='condition'?'가격 조건':event.severity==='recovery'?'수집 복구':'수집 상태'} · {kstTime(event.occurred_at,true)} KST</span><p>{event.message}</p></div>{!read.has(event.id)&&<button className="text-button" onClick={()=>markRead(event.id)} aria-label={`${event.message} 읽음`}>읽음</button>}</article>)}</div>
      <div className="context-note"><Icon name="info"/><p>가격 조건은 이 브라우저에서 화면이 열려 있는 동안 확인합니다. 등록 시 이미 만족하면 1회 알리며, 조건을 벗어났다가 다시 진입할 때 최소 10분 간격으로 알립니다. 오래된 시세는 평가하지 않습니다. 조건·읽음 상태·알림함은 이 브라우저에 저장되며 최근 100건을 보관합니다. 서버 수집 실패·복구 이력은 90일 보관합니다.</p></div>
      {storageError&&<p className="form-error" role="alert">브라우저 저장소를 사용할 수 없어 설정이 새로 고침 후 유지되지 않을 수 있습니다.</p>}
    </>}
  </Card>;
}
