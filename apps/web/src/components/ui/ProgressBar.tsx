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
  const barColor = clamped === 100 ? 'bg-green-500' : 'bg-orange-500';

  return (
    <div className={className}>
      {(label || showPercent) && (
        <div className="flex justify-between items-center mb-1">
          {label && <span className="text-xs text-gray-500">{label}</span>}
          {showPercent && (
            <span className="text-xs font-medium text-gray-700">{clamped}%</span>
          )}
        </div>
      )}
      <div
        className={`w-full bg-gray-200 rounded-full ${barHeight}`}
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
