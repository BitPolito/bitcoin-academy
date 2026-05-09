import type { AuthOptions } from 'next-auth';
import type { JWT } from 'next-auth/jwt';
import CredentialsProvider from 'next-auth/providers/credentials';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ACCESS_TOKEN_TTL_MS = 30 * 60 * 1000; // 30 min — must match backend ACCESS_TOKEN_EXPIRE_MINUTES
const REFRESH_BUFFER_MS = 60 * 1000; // refresh 1 min before expiry

async function refreshAccessToken(token: JWT): Promise<JWT> {
  try {
    const res = await fetch(`${API_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: token.refreshToken }),
    });

    const data = await res.json();
    if (!res.ok) throw data;

    return {
      ...token,
      accessToken: data.access_token,
      refreshToken: data.refresh_token ?? token.refreshToken,
      accessTokenExpires: Date.now() + ACCESS_TOKEN_TTL_MS,
      error: undefined,
    };
  } catch {
    return { ...token, error: 'RefreshAccessTokenError' };
  }
}

export const authOptions: AuthOptions = {
  providers: [
    CredentialsProvider({
      name: 'credentials',
      credentials: {
        email: { label: 'Email', type: 'email' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          throw new Error('Email and password are required');
        }

        try {
          const res = await fetch(`${API_URL}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
            }),
          });

          if (!res.ok) {
            const error = await res.json().catch(() => ({}));
            throw new Error(error.detail || 'Invalid email or password');
          }

          const data = await res.json();

          return {
            id: data.user?.id || data.id,
            email: data.user?.email || credentials.email,
            name: data.user?.display_name || null,
            accessToken: data.access_token || data.tokens?.access_token,
            refreshToken: data.refresh_token || data.tokens?.refresh_token,
            role: data.user?.role || 'student',
            displayName: data.user?.display_name || null,
          };
        } catch (error) {
          if (error instanceof Error) throw error;
          throw new Error('Authentication failed');
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        return {
          ...token,
          accessToken: user.accessToken,
          refreshToken: user.refreshToken,
          role: user.role,
          displayName: user.displayName,
          accessTokenExpires: Date.now() + ACCESS_TOKEN_TTL_MS,
        };
      }

      // Token still valid
      if (Date.now() < (token.accessTokenExpires ?? 0) - REFRESH_BUFFER_MS) {
        return token;
      }

      // Token expired — attempt refresh
      return refreshAccessToken(token);
    },
    async session({ session, token }) {
      session.user.id = token.sub;
      session.user.accessToken = token.accessToken;
      session.user.role = token.role;
      session.user.displayName = token.displayName;
      session.error = token.error;
      return session;
    },
  },
  pages: {
    signIn: '/login',
    error: '/login',
  },
  session: {
    strategy: 'jwt',
    maxAge: 7 * 24 * 60 * 60, // 7 days — refresh token lifetime
  },
  secret: process.env.NEXTAUTH_SECRET,
};
