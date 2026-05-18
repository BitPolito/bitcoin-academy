'use client';

interface ProgressBarProps {
  percent: number;
  label?: string;
  showPercent?: boolean;
  size?: 'sm' | 'md';
  className?: string;
}

export function ProgressBar({
  percent,
  label,
  showPercent = true,
  size = 'sm',
  className = '',
}: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, percent));
  const barHeight = size === 'sm' ? 'h-1.5' : 'h-2.5';
  const barColor = clamped === 100 ? 'bg-[#1a7f3a]' : 'bg-[#a55a00]';

  return (
    <div className={className}>
      {(label || showPercent) && (
        <div className="flex justify-between items-center mb-1">
          {label && <span className="text-xs opacity-60">{label}</span>}
          {showPercent && <span className="text-xs font-medium opacity-70">{clamped}%</span>}
        </div>
      )}
      <div
        className={`w-full bg-blue-dark/10 rounded-full ${barHeight}`}
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? `Progress: ${clamped}%`}
      >
        <div
          className={`${barColor} ${barHeight} rounded-full transition-all duration-500`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
