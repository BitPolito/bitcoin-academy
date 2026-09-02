'use client';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

const SIZE_MAP = {
  sm: 'w-4 h-4 border-2',
  md: 'w-8 h-8 border-2',
  lg: 'w-10 h-10 border-2',
};

export function Spinner({ size = 'md', label }: SpinnerProps) {
  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className={`${SIZE_MAP[size]} border-blue-dark/30 border-t-blue-dark dark:border-white/30 dark:border-t-white rounded-full animate-spin`}
        role="status"
        aria-label={label ?? 'Loading'}
      />
      {label && (
        <p className="font-mono text-[11px] tracking-[0.18em] uppercase opacity-60">{label}</p>
      )}
    </div>
  );
}
