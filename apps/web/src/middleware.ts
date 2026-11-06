import { authMiddleware } from '@/lib/middleware/auth-guard';

// Next.js explicitly looks for a named 'middleware' export
export { authMiddleware as middleware };

// Next.js 15+ strictly requires config to be a static object in this file
export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
