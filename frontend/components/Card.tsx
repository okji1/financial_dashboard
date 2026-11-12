import type { ReactNode } from 'react';
import { Icon, type IconName } from './ui';

export default function Card({ title, children, eyebrow, icon, action, id, className = '' }: {
  title: string; children: ReactNode; eyebrow?: string; icon?: IconName; action?: ReactNode; id?: string; className?: string;
}) {
  return <section className={`panel ${className}`} id={id} aria-label={title}>
    <header className="panel-header"><div className="panel-heading">{icon && <span className="panel-icon"><Icon name={icon}/></span>}<div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2></div></div>{action}</header>
    <div className="panel-content">{children}</div>
  </section>;
}
