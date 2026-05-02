'use client';

import type { Badge } from '@/lib/services/progress';

interface BadgeDisplayProps {
  badge: Badge;
  size?: 'sm' | 'md';
}

export function BadgeDisplay({ badge, size = 'md' }: BadgeDisplayProps) {
  const iconSize = size === 'sm' ? 'text-lg' : 'text-3xl';
  const padding = size === 'sm' ? 'px-2 py-1' : 'px-3 py-2';

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-lg bg-yellow-50 border border-yellow-200 ${padding}`}
      title={badge.description}
      role="img"
      aria-label={`Badge: ${badge.name}`}
    >
      <span className={iconSize} aria-hidden="true">
        {badge.icon}
      </span>
      <div>
        <p className="text-xs font-semibold text-yellow-800">{badge.name}</p>
        {size === 'md' && (
          <p className="text-xs text-yellow-600">{badge.description}</p>
        )}
      </div>
    </div>
  );
}
