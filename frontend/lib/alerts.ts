import type { PremiumData } from './market-data';

export const ALERT_STORAGE_KEY='gold-desk-alerts-v1';
export type Metric='price'|'premium';
export interface AlertRule {
  id:string; metric:Metric; operator:'gte'|'lte'; threshold:number; enabled:boolean;
  matched:boolean; lastFiredAt:number|null;
}
export interface InboxEvent { id:string; kind:'condition'|'system'; severity:'warning'|'recovery'; occurred_at:string; message:string }
export interface AlertState { rules:AlertRule[]; events:InboxEvent[]; readIds:string[] }
export const emptyAlerts=():AlertState=>({rules:[],events:[],readIds:[]});
export const ruleLabel=(rule:AlertRule)=>`${rule.metric==='price'?'국내 금 현물':'국내외 가격 차이'} ${new Intl.NumberFormat('ko-KR',{maximumFractionDigits:4}).format(rule.threshold)}${rule.metric==='price'?'원/g':'%'} ${rule.operator==='gte'?'이상':'이하'}`;

export function restoreAlerts(raw:string|null):AlertState {
  if(!raw)return emptyAlerts();
  try {
    const value=JSON.parse(raw);
    if(!value || !Array.isArray(value.rules) || !Array.isArray(value.events) || !Array.isArray(value.readIds))return emptyAlerts();
    return {
      rules:value.rules.filter((r:AlertRule)=>r && typeof r.id==='string' && r.id.length<100 && ['price','premium'].includes(r.metric) && ['gte','lte'].includes(r.operator)
        && typeof r.threshold==='number' && Number.isFinite(r.threshold) && (r.metric!=='price'||r.threshold>0)
        && typeof r.enabled==='boolean' && typeof r.matched==='boolean' && (r.lastFiredAt===null||Number.isFinite(r.lastFiredAt))).slice(0,10),
      events:value.events.filter((e:InboxEvent)=>e && typeof e.id==='string' && e.id.length<200 && ['condition','system'].includes(e.kind)
        && ['warning','recovery'].includes(e.severity) && typeof e.message==='string' && e.message.length<500 && Number.isFinite(Date.parse(e.occurred_at))).slice(0,100),
      readIds:value.readIds.filter((id:unknown)=>typeof id==='string'&&id.length<200).slice(0,200),
    };
  } catch{return emptyAlerts();}
}

export function addEvents(state:AlertState,events:InboxEvent[]):AlertState {
  const map=new Map(state.events.map(event=>[event.id,event]));
  let added=false;
  for(const event of events)if(!map.has(event.id)){map.set(event.id,event);added=true;}
  if(!added)return state;
  const next=Array.from(map.values()).sort((a,b)=>Date.parse(b.occurred_at)-Date.parse(a.occurred_at)).slice(0,100);
  const ids=new Set(next.map(event=>event.id));
  return {...state,events:next,readIds:state.readIds.filter(id=>ids.has(id))};
}

export function evaluateRules(state:AlertState,quote:PremiumData|null,now:number):AlertState {
  if(!quote)return state;
  const age=now-Date.parse(quote.timestamp);
  if(!Number.isFinite(age)||age < -5000||age>90000)return state;
  let changed=false;
  const events:InboxEvent[]=[];
  const rules=state.rules.map(rule=>{
    if(!rule.enabled)return rule;
    const value=rule.metric==='price'?quote.domestic_gold_price:quote.premium_percentage;
    if(!Number.isFinite(value))return rule;
    const matched=rule.operator==='gte'?value>=rule.threshold:value<=rule.threshold;
    if(matched===rule.matched)return rule;
    changed=true;
    const fire=matched && (rule.lastFiredAt===null||now-rule.lastFiredAt>=600000);
    if(fire)events.push({id:`condition:${rule.id}:${quote.timestamp}`,kind:'condition',severity:'warning',occurred_at:new Date(now).toISOString(),
      message:`${ruleLabel(rule)} 조건 충족 · 현재 ${new Intl.NumberFormat('ko-KR',{maximumFractionDigits:4}).format(value)}${rule.metric==='price'?'원/g':'%'}`});
    return {...rule,matched,lastFiredAt:fire?now:rule.lastFiredAt};
  });
  return changed?addEvents({...state,rules},events):state;
}
