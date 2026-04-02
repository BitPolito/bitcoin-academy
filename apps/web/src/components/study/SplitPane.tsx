'use client';

import { useCallback, useRef, useState, type ReactNode } from 'react';

interface SplitPaneProps {
  left: ReactNode;
  right: ReactNode;
  defaultLeftPercent?: number;
  minLeftPercent?: number;
  maxLeftPercent?: number;
}

export function SplitPane({
  left,
  right,
  defaultLeftPercent = 50,
  minLeftPercent = 25,
  maxLeftPercent = 75,
}: SplitPaneProps) {
  const [leftPercent, setLeftPercent] = useState(defaultLeftPercent);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;

      const onMouseMove = (ev: MouseEvent) => {
        if (!dragging.current || !containerRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        const percent = ((ev.clientX - rect.left) / rect.width) * 100;
        setLeftPercent(Math.min(maxLeftPercent, Math.max(minLeftPercent, percent)));
      };

      const onMouseUp = () => {
        dragging.current = false;
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };

      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    },
    [minLeftPercent, maxLeftPercent]
  );

  return (
    <div ref={containerRef} className="flex h-full w-full overflow-hidden">
      <div style={{ width: `${leftPercent}%` }} className="overflow-auto">
        {left}
      </div>

      <div
        onMouseDown={onMouseDown}
        className="flex-shrink-0 w-1.5 cursor-col-resize bg-gray-200 hover:bg-orange-300 active:bg-orange-400 transition-colors relative group"
      >
        <div className="absolute inset-y-0 -left-1 -right-1" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-8 w-1 rounded-full bg-gray-400 group-hover:bg-orange-500 transition-colors" />
      </div>

      <div style={{ width: `${100 - leftPercent}%` }} className="overflow-auto">
        {right}
      </div>
    </div>
  );
}
