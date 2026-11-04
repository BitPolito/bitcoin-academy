import { authMiddleware } from '@/lib/middleware/auth-guard';

export default authMiddleware;

export const config = {
  matcher: ['/dashboard/:path*', '/courses/:path*'],
};