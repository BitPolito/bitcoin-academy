import 'next-auth';
import 'next-auth/jwt';

declare module 'next-auth' {
  interface Session {
    user: {
      id?: string;
      email?: string | null;
      name?: string | null;
      image?: string | null;
      accessToken?: string;
      role?: string;
      displayName?: string | null;
    };
    error?: string;
  }

  interface User {
    accessToken?: string;
    refreshToken?: string;
    role?: string;
    displayName?: string | null;
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    role?: string;
    displayName?: string | null;
    accessTokenExpires?: number;
    error?: string;
  }
}
