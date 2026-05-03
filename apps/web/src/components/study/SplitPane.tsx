'use client';

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

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
  const [isMobile, setIsMobile] = useState(false);
  const [activeTab, setActiveTab] = useState<'left' | 'right'>('right');
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

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

  if (isMobile) {
    return (
      <div className="flex flex-col h-full w-full overflow-hidden">
        {/* Tab bar */}
        <div className="flex-shrink-0 flex b-thin-b">
          <button
            onClick={() => setActiveTab('left')}
            className={`flex-1 py-2 font-mono text-[11px] tracking-[0.14em] uppercase transition-colors ${
              activeTab === 'left'
                ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                : 'hover:bg-blue-dark/5 dark:hover:bg-white/10'
            }`}
          >
            Sources
          </button>
          <button
            onClick={() => setActiveTab('right')}
            className={`flex-1 py-2 font-mono text-[11px] tracking-[0.14em] uppercase transition-colors ${
              activeTab === 'right'
                ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                : 'hover:bg-blue-dark/5 dark:hover:bg-white/10'
            }`}
          >
            Study
          </button>
        </div>
        {/* Active pane */}
        <div className="flex-1 overflow-auto min-h-0">
          {activeTab === 'left' ? left : right}
        </div>
      </div>
    );
  }

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
