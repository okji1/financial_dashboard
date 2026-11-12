import type { ReactNode } from 'react';
import type { Remote } from '../lib/market-data';

export type IconName = 'grid' | 'gold' | 'globe' | 'exchange' | 'ratio' | 'activity' | 'layers' | 'database' | 'refresh' | 'arrow' | 'chevron' | 'sun' | 'moon' | 'info' | 'clock' | 'bell';
const paths: Record<IconName, ReactNode> = {
  bell: <><path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5Zm5 3h4"/><path d="M12 2v2"/></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  gold: <><path d="m7 5-4 14h18L17 5Z"/><path d="M7 5h10M4.5 14h15M12 5v9"/></>,
  globe: <><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/></>,
  exchange: <><path d="M4 7h15m-4-4 4 4-4 4M20 17H5m4-4-4 4 4 4"/></>,
  ratio: <><path d="m5 19 14-14"/><circle cx="6.5" cy="6.5" r="3"/><circle cx="17.5" cy="17.5" r="3"/></>,
  activity: <path d="M3 12h4l3-8 4 16 3-8h4"/>,
  layers: <><path d="m12 3 10 5-10 5L2 8Zm-9 9 9 5 9-5M3 17l9 5 9-5"/></>,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/></>,
  refresh: <><path d="M20 7a8 8 0 0 0-14-2L3 8m0-5v5h5M4 17a8 8 0 0 0 14 2l3-3m0 5v-5h-5"/></>,
  arrow: <path d="M5 12h14m-5-5 5 5-5 5"/>,
  chevron: <path d="m6 9 6 6 6-6"/>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></>,
  moon: <path d="M20 14A8 8 0 0 1 10 4a9 9 0 1 0 10 10Z"/>,
  info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.5"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
};
export function Icon({ name, className = '' }: { name: IconName; className?: string }) {
  return <svg className={`icon ${className}`} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
export function RemoteMessage({ remote, empty = '현재 제공되는 데이터가 없습니다.' }: { remote: Remote<unknown>; empty?: string }) {
  if (remote.loading) return <div className="loading-block" role="status"><span className="skeleton skeleton-wide"/><span className="skeleton skeleton-short"/><p>데이터를 확인하고 있습니다.</p></div>;
  const missing = remote.error?.status === 404;
  return <div className={`empty-state ${missing ? '' : 'is-error'}`} role={missing ? 'status' : 'alert'}><Icon name={missing ? 'layers' : 'info'}/><p>{missing ? empty : remote.error?.message || empty}</p><small>{missing ? '실제 데이터가 제공되면 표시됩니다.' : '상단의 새로 고침으로 다시 확인할 수 있습니다.'}</small></div>;
}
export function Badge({ children, tone = 'muted' }: { children: ReactNode; tone?: 'gold' | 'positive' | 'warning' | 'muted' }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
