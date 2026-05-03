import { ReactNode } from 'react';
import { BrandMark } from '@/components/ui/BrandMark';

interface AuthLayoutProps {
  children: ReactNode;
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="min-h-screen bg-surface dark:bg-[#0a0a0a] dotgrid flex flex-col">
      {/* Header — mirrors TopBar structure and styling */}
      <header className="sticky top-0 z-10 bg-surface dark:bg-blue-dark b-thin-b">
        <div className="max-w-8xl mx-auto px-6 h-14 flex items-center">
          <BrandMark />
        </div>
      </header>

      {/* Form area */}
      <main className="flex-1 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full space-y-6 page-fade">
          <p className="text-center font-mono text-[11px] tracking-wide uppercase text-[#001CE0]/50 dark:text-white/40">
            Learn Bitcoin with interactive courses
          </p>
          {children}
        </div>
      </main>
    </div>
  );
}
