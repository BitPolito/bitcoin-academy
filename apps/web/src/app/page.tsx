'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';

export default function Home() {
  const router = useRouter();
  const { status } = useSession();

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/login');
    }
  }, [status, router]);

  // Show loading state while checking authentication
  if (status === 'loading' || status === 'unauthenticated') {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center p-24 bg-gradient-to-b from-dark to-light">
        <div className="text-center">
          <p className="text-gray-500">Redirecting...</p>
        </div>
      </main>
    );
  }

  // If authenticated, redirect to dashboard
  useEffect(() => {
    if (status === 'authenticated') {
      router.push('/dashboard');
    }
  }, [status, router]);

  return null;
}
