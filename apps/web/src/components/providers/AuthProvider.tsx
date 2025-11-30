'use client';

/**
 * Session provider wrapper for NextAuth.js
 * Wraps the application with the SessionProvider to enable authentication
 */
import { SessionProvider } from 'next-auth/react';
import { ReactNode } from 'react';

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * Authentication provider component
 * Wraps children with NextAuth SessionProvider
 */
export function AuthProvider({ children }: AuthProviderProps) {
  return <SessionProvider>{children}</SessionProvider>;
}

export default AuthProvider;
