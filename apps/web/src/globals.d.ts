declare module '*.css';

// Environment variables
declare namespace NodeJS {
  interface ProcessEnv {
    NEXT_PUBLIC_API_URL?: string;
    NEXTAUTH_URL?: string;
    NEXTAUTH_SECRET?: string;
  }
}
