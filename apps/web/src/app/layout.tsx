import type { Metadata, Viewport } from 'next';
import './globals.css';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { SessionErrorGuard } from '@/components/providers/SessionErrorGuard';

export const metadata: Metadata = {
  title: 'BitPolito Academy',
  description: 'Learn Bitcoin with interactive courses',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <SessionErrorGuard />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
