'use client';

import { useSession, signOut } from 'next-auth/react';
import { useEffect } from 'react';

export function SessionErrorGuard() {
  const { data: session } = useSession();

  useEffect(() => {
    if (session?.error === 'RefreshAccessTokenError') {
      signOut({ callbackUrl: '/login' });
    }
  }, [session?.error]);

  return null;
}
