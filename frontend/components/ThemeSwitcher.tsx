'use client';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { Icon } from './ui';

export function ThemeSwitcher() {
  const [mounted, setMounted] = useState(false);
  const { resolvedTheme, setTheme } = useTheme();
  useEffect(() => setMounted(true), []);
  if (!mounted) return <span className="icon-button theme-placeholder" aria-hidden="true"/>;
  const dark = resolvedTheme === 'dark';
  return <button className="icon-button" onClick={() => setTheme(dark ? 'light' : 'dark')}
    aria-label={dark ? '밝은 테마로 전환' : '어두운 테마로 전환'} title={dark ? '밝은 테마' : '어두운 테마'}>
    <Icon name={dark ? 'sun' : 'moon'}/>
  </button>;
}
