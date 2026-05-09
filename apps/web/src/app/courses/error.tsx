'use client';

import { useEffect } from 'react';

export default function CoursesError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[CoursesError]', error);
  }, [error]);

  return (
    <main className="max-w-8xl mx-auto px-6 py-16 text-center">
      <p className="text-sm opacity-70 mb-4">Something went wrong loading this page.</p>
      <button
        onClick={reset}
        className="font-mono text-[11px] tracking-[0.14em] uppercase px-4 py-2 b-thin rounded-md hover:bg-blue-dark/5 dark:hover:bg-white/10 transition-colors"
      >
        Try again
      </button>
    </main>
  );
}
