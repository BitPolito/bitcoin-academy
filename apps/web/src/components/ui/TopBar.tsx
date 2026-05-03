'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { BrandMark } from './BrandMark';

export function TopBar() {
  const pathname = usePathname();
  const { data: session } = useSession();
  const [dark, setDark] = useState(false);

  // Sync with system preference and persisted value on mount
  useEffect(() => {
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = saved === 'dark' || (!saved && prefersDark);
    setDark(isDark);
    document.documentElement.classList.toggle('dark', isDark);
  }, []);

  function toggleDark() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
  }

  const courseMatch = pathname.match(/^\/courses\/([^/]+)/);
  const courseId = courseMatch?.[1];

  const isStudy = !!courseId && pathname.includes('/study');
  const isPreview = !!courseId && pathname.includes('/preview');
  const isWorkspace = !!courseId && !isStudy && !isPreview;
  const isCourses = !courseId;

  const tabs = [
    { id: 'courses',   label: 'Courses',   href: '/courses',                        active: isCourses },
    ...(courseId ? [
      { id: 'workspace', label: 'Workspace', href: `/courses/${courseId}`,            active: isWorkspace },
      { id: 'study',     label: 'Study',     href: `/courses/${courseId}/study`,      active: isStudy },
    ] : []),
  ];

  const isDebug = !!courseId && pathname.includes('/debug');

  const name = (session?.user as any)?.name || (session?.user as any)?.email || '';
  const initials = name
    .split(/[\s@]/)
    .filter(Boolean)
    .map((p: string) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase() || 'U';

  return (
    <header className="sticky top-0 z-40 bg-surface dark:bg-blue-dark b-thin-b">
      <div className="max-w-8xl mx-auto px-6 h-14 flex items-center gap-6">
        <BrandMark />

        <nav className="flex items-center gap-1 ml-2">
          {tabs.map((tab) => (
            <Link
              key={tab.id}
              href={tab.href}
              className={`px-3 h-8 rounded-md font-mono text-[11px] tracking-[0.14em] uppercase whitespace-nowrap transition-all inline-flex items-center ${
                tab.active
                  ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                  : 'hover:bg-blue-dark/5 dark:hover:bg-white/10'
              }`}
            >
              {tab.label}
            </Link>
          ))}
        </nav>

        {process.env.NODE_ENV === 'development' && courseId && (
          <Link
            href={`/courses/${courseId}/debug`}
            className={`px-3 h-8 rounded-md font-mono text-[11px] tracking-[0.14em] uppercase whitespace-nowrap transition-all inline-flex items-center ${
              isDebug
                ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                : 'opacity-50 hover:opacity-100 hover:bg-blue-dark/5 dark:hover:bg-white/10'
            }`}
          >
            Debug
          </Link>
        )}

        <div className="ml-auto flex items-center gap-2">
          {/* Search placeholder */}
          <div className="hidden md:flex items-center gap-2 px-3 h-8 b-thin rounded-md w-56 opacity-60 cursor-not-allowed select-none">
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5"/>
            </svg>
            <span className="font-mono text-[11px]">Search…</span>
            <span className="ml-auto mono text-[10px] b-thin px-1.5 rounded">⌘K</span>
          </div>

          {/* Dark mode toggle */}
          <button
            onClick={toggleDark}
            className="h-8 w-8 b-thin rounded-md flex items-center justify-center hover:bg-blue-dark/5 dark:hover:bg-white/10 transition-colors"
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label="Toggle dark mode"
          >
            {dark ? (
              /* Sun icon */
              <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor">
                <circle cx="12" cy="12" r="4"/>
                <g stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <line x1="12" y1="2"  x2="12" y2="5"/>
                  <line x1="12" y1="19" x2="12" y2="22"/>
                  <line x1="2"  y1="12" x2="5"  y2="12"/>
                  <line x1="19" y1="12" x2="22" y2="12"/>
                  <line x1="4.5"  y1="4.5"  x2="6.5"  y2="6.5"/>
                  <line x1="17.5" y1="17.5" x2="19.5" y2="19.5"/>
                  <line x1="4.5"  y1="19.5" x2="6.5"  y2="17.5"/>
                  <line x1="17.5" y1="6.5"  x2="19.5" y2="4.5"/>
                </g>
              </svg>
            ) : (
              /* Moon icon */
              <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor">
                <path d="M21 12.8A9 9 0 0 1 11.2 3a7 7 0 1 0 9.8 9.8z"/>
              </svg>
            )}
          </button>

          {/* User avatar */}
          <div
            className="h-8 w-8 b-thin rounded-md flex items-center justify-center font-mono text-[11px] font-semibold"
            title={name}
          >
            {initials}
          </div>
        </div>
      </div>
    </header>
  );
}
