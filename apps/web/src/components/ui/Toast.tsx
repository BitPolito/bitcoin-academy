'use client';

import { createContext, useCallback, useContext, useRef, useState } from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────

export type ToastType = 'ok' | 'err' | 'warn';

interface ToastMsg {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType) => void;
}

// ── Context ───────────────────────────────────────────────────────────────────

const ToastContext = createContext<ToastContextValue>({ showToast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

// ── Style map ─────────────────────────────────────────────────────────────────

const TYPE_CONFIG: Record<ToastType, { bg: string; icon: string }> = {
  ok:   { bg: '#1a7f3a', icon: '✓' },
  err:  { bg: '#b3261e', icon: '✕' },
  warn: { bg: '#a55a00', icon: '!' },
};

// ── Provider ──────────────────────────────────────────────────────────────────

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  const counter = useRef(0);

  const showToast = useCallback((message: string, type: ToastType = 'ok') => {
    const id = ++counter.current;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {toasts.length > 0 && (
        <div
          className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none"
          aria-live="assertive"
          aria-label="Notifications"
        >
          {toasts.map((t) => {
            const { bg, icon } = TYPE_CONFIG[t.type];
            return (
              <div
                key={t.id}
                role="alert"
                className="pointer-events-auto flex items-center gap-3 px-4 py-2.5 rounded-lg shadow-lg text-white font-mono text-[12px] max-w-xs"
                style={{ background: bg }}
              >
                <span className="text-sm font-bold flex-shrink-0" aria-hidden="true">
                  {icon}
                </span>
                <span className="flex-1 leading-snug break-words">{t.message}</span>
                <button
                  onClick={() => dismiss(t.id)}
                  className="flex-shrink-0 opacity-70 hover:opacity-100 transition-opacity ml-1"
                  aria-label="Dismiss notification"
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      )}
    </ToastContext.Provider>
  );
}
