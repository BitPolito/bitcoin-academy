import Link from 'next/link';

export function BrandMark() {
  return (
    <Link href="/courses" className="inline-flex items-center gap-3">
      <svg viewBox="0 0 36 24" className="w-9 h-6 ink" fill="currentColor" aria-hidden>
        <rect x="0"  y="2"  width="2" height="14"/>
        <rect x="2"  y="0"  width="2" height="2"/>
        <rect x="4"  y="2"  width="2" height="2"/>
        <rect x="6"  y="4"  width="2" height="14"/>
        <rect x="4"  y="14" width="2" height="2"/>
        <rect x="2"  y="16" width="2" height="2"/>
        <rect x="10" y="6"  width="2" height="12"/>
        <rect x="12" y="4"  width="2" height="2"/>
        <rect x="14" y="6"  width="2" height="6"/>
        <rect x="12" y="12" width="2" height="2"/>
        <rect x="20" y="2"  width="2" height="20"/>
        <rect x="22" y="0"  width="2" height="2"/>
        <rect x="22" y="22" width="2" height="2"/>
        <rect x="28" y="6"  width="2" height="12"/>
        <rect x="30" y="4"  width="2" height="2"/>
        <rect x="32" y="6"  width="2" height="12"/>
        <rect x="30" y="18" width="2" height="2"/>
      </svg>
      <span className="font-mono text-[11px] tracking-[0.18em] uppercase ink font-semibold hidden sm:inline">
        BitPolito · Academy
      </span>
    </Link>
  );
}
