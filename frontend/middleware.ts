import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const PROTECTED_ROUTES = ['/dashboard', '/setup-2fa', '/activity', '/shared-files', '/admin'];
const AUTH_ROUTES = ['/login', '/login-2fa', '/register'];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasAuthCookie = request.cookies.get('securedrop_token_present')?.value === '1';

  if (PROTECTED_ROUTES.some((route) => pathname.startsWith(route)) && !hasAuthCookie) {
    const loginUrl = new URL('/login', request.url);
    return NextResponse.redirect(loginUrl);
  }

  if (AUTH_ROUTES.some((route) => pathname.startsWith(route)) && hasAuthCookie) {
    const dashboardUrl = new URL('/dashboard', request.url);
    return NextResponse.redirect(dashboardUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/setup-2fa', '/activity/:path*', '/shared-files/:path*', '/admin/:path*', '/login', '/login-2fa', '/register'],
};