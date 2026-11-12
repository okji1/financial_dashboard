'use client';
import { useState } from 'react';
import { MarketDataProvider, useMarketData, number, ageSeconds, kstTime } from '../lib/market-data';
import GoldPremium from './GoldPremium';
import InvestmentStrategy from './InvestmentStrategy';
import GoldAnalysis from './GoldAnalysis';
import ActiveContractManager from './ActiveContractManager';
import DataSources from './DataSources';
import KRXGoldDaily from './KRXGoldDaily';
import KRXHistoryChart from './KRXHistoryChart';
import AlertCenter from './AlertCenter';
import { ThemeSwitcher } from './ThemeSwitcher';
import { Icon, type IconName } from './ui';

const links: { href: string; icon: IconName; label: string; index: string }[] = [
  { href: '#overview', icon: 'grid', label: '시장 개요', index: '01' },
  { href: '#analysis', icon: 'activity', label: '시장 분석', index: '02' },
  { href: '#futures', icon: 'gold', label: '선물 계약', index: '03' },
  { href: '#history', icon: 'activity', label: '가격 추이', index: '04' },
  { href: '#alerts', icon: 'bell', label: '알림함', index: '05' },
  { href: '#sources', icon: 'database', label: '데이터 출처', index: '06' },
];
function DashboardContent() {
  const [unread,setUnread]=useState(0);
  const market = useMarketData();
  const { premium, now } = market;
  const data = premium.data;
  const age = ageSeconds(data?.timestamp, now);
  const remotes = [premium, market.strategy, market.analysis, market.active, market.candidates, market.pressure, market.krx, market.systemAlerts];
  const loading = remotes.some(item => item.loading);
  const errors = remotes.some(item => item.error && item.error.status !== 404);
  const fresh = data && age !== null && age <= 90;
  const status = !data && loading ? '데이터 확인 중' : errors ? '일부 응답 확인 필요' : fresh ? '최근 수집 데이터' : '수집 시각 확인 필요';
  const metrics: { key: string; label: string; icon: IconName; value: string; unit: string; source: string; tag: string }[] = [
    { key: 'domestic', label: '국내 금 현물', icon: 'gold', value: number(data?.domestic_gold_price), unit: '원 / g', source: '네이버 금융 · 금 현물', tag: 'DOMESTIC' },
    { key: 'international', label: '국제 금 선물', icon: 'globe', value: number(data?.london_gold_usd, 2), unit: '달러 / oz', source: '네이버 금융 · COMEX', tag: 'GLOBAL' },
    { key: 'exchange', label: '원·달러 환율', icon: 'exchange', value: number(data?.exchange_rate, 2), unit: '원 / USD', source: '한국수출입은행 · 기준환율', tag: 'CURRENCY' },
    { key: 'premium', label: '국내외 가격 차이', icon: 'ratio', value: data ? `${data.premium_percentage > 0 ? '+' : ''}${number(data.premium_percentage, 2)}` : '—', unit: '%', source: '국제 선물 · 국내 현물 참고 비교', tag: 'PRICE GAP' },
  ];
  return <div className="dashboard-shell">
    <a className="skip-link" href="#overview">본문으로 바로가기</a>
    <aside className="sidebar"><a className="brand" href="#overview" aria-label="Financial Dashboard 시장 개요"><span className="brand-mark"><small>79</small>Au</span><span>GOLD DESK<small>FINANCIAL DASHBOARD</small></span></a>
      <div className="nav-label">WORKSPACE</div><nav aria-label="주요 메뉴">{links.map(link => <a className={`nav-link ${link.index === '01' ? 'selected' : ''}`} key={link.href} href={link.href}><Icon name={link.icon}/><span>{link.label}</span><small>{link.index}</small></a>)}</nav>
      <div className="sidebar-note"><span className="tiny-label">THE PRECIOUS PERSPECTIVE</span><div className="sidebar-rule"/><p>가격 너머의 맥락을<br/>더 선명하게.</p><span>국내외 금 시장 데이터 워크스페이스</span></div>
      <div className="sidebar-footer"><Icon name="globe"/><span>KRW · USD</span><span className="version-label">GOLD / 01</span></div>
    </aside>
    <div className="workspace"><header className="topbar"><div className="breadcrumb"><span className="mobile-brand">Au</span><span>Financial Dashboard</span><span className="breadcrumb-divider">/</span><strong>Market overview</strong></div><div className="topbar-actions"><span className="topbar-time"><Icon name="clock"/>{now === null ? '한국시간' : kstTime(now)}<small>KST</small></span><a className="notification-link" href="#alerts" aria-label={`알림함, 읽지 않은 알림 ${unread}건`}><Icon name="bell"/>{unread>0&&<span>{unread}</span>}</a><ThemeSwitcher/></div></header>
      <main className="dashboard-main"><section className="hero" id="overview"><div><p className="eyebrow">GOLD MARKET OVERVIEW</p><h1>금 시장, 한눈에.</h1><p className="hero-description">시세와 환율, 국내외 가격 차이를 함께 확인하세요.</p></div><div className="hero-actions"><span className={`connection-status ${errors ? 'is-warning' : fresh ? 'is-connected' : ''}`} role="status"><i/>{status}</span><button className="button button-primary" onClick={market.refresh} disabled={loading}><Icon name="refresh" className={loading ? 'spinning' : ''}/>{loading ? '확인 중' : '새로 고침'}</button></div></section>
      <nav className="mobile-nav" aria-label="모바일 메뉴">{links.map(link => <a key={link.href} href={link.href}><Icon name={link.icon}/>{link.label}</a>)}</nav>
      <div className="overview-meta"><span><span className="status-dot"/>현재 제공되는 시세를 30초마다 확인합니다</span><span>{data ? `시세 묶음 수집 ${kstTime(data.timestamp)} KST` : '시세 수집 시각 확인 중'}</span></div>
      <section className="metrics-grid" aria-label="핵심 시세 지표">{metrics.map(metric => <article key={metric.key} className={`metric-card ${metric.key === 'premium' ? 'metric-featured' : ''}`}><div className="metric-top"><span className="metric-label">{metric.label}</span><Icon name={metric.icon}/></div><div className="metric-number" data-testid={`metric-${metric.key}`}>{premium.loading && !data ? <span className="skeleton skeleton-number"/> : metric.value}<span>{metric.unit}</span></div><div className="metric-bottom"><span>{metric.source}</span><small>{metric.tag}</small></div></article>)}</section>
      {premium.error && <div className="data-alert" role="alert" data-testid="market-error"><Icon name="info"/><div><strong>시세를 불러오지 못했습니다.</strong><p>{premium.error.message}</p></div><button className="text-button" onClick={market.refresh} disabled={loading}>다시 확인<Icon name="arrow"/></button></div>}
      {data && !fresh && now !== null && <div className="data-alert"><Icon name="clock"/><p>표시 중인 수집 시각을 다시 확인해 주세요. 오래된 데이터로 새 해석을 제공하지 않습니다.</p></div>}
      <div className="primary-grid"><GoldPremium/><InvestmentStrategy/></div>
      <GoldAnalysis/>
      <ActiveContractManager/>
      <KRXGoldDaily/>
      <KRXHistoryChart/>
      <AlertCenter onUnreadChange={setUnread}/>
      <DataSources/>
      <footer className="dashboard-footer"><span>GOLD DESK <i/> Financial Dashboard</span><p>수집 시세를 바탕으로 한 참고 정보입니다. 실제 거래 전 공급자의 기준 시각과 체결 가능 가격을 확인하세요.</p><a href="#overview">맨 위로<Icon name="arrow"/></a></footer>
      </main>
    </div>
  </div>;
}
export default function Dashboard() {
  return <MarketDataProvider><DashboardContent/></MarketDataProvider>;
}
