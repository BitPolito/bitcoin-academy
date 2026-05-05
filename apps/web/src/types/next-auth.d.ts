import type { DefaultSession } from 'next-auth';

declare module 'next-auth' {
  interface Session {
    user: {
      accessToken: string;
      refreshToken: string;
      role: string;
      displayName: string | null;
    } & DefaultSession['user'];
  }
}
