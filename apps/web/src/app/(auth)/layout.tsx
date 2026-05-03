import { ReactNode } from 'react';
import { BrandMark } from '@/components/ui/BrandMark';

interface AuthLayoutProps {
  children: ReactNode;
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface dark:bg-[#0a0a0a] py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div className="flex flex-col items-center gap-3">
          <BrandMark />
          <p className="font-mono text-[11px] tracking-wide uppercase text-[#001CE0]/50 dark:text-white/40">
            Learn Bitcoin with interactive courses
          </p>
        </div>
        {children}
      </div>
    </div>
  );
}
