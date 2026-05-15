"use client";

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ReactNode, useEffect, useMemo, useState } from 'react';

import {
  clearPending2FA,
  clearToken,
  getCurrentUserRole,
  getRefreshToken,
  getToken,
  logout,
} from '@/lib/api';

type AppShellProps = {
  children: ReactNode;
};

type NavItem = {
  href: string;
  label: string;
  icon: ReactNode;
};

const PUBLIC_PATH_PREFIXES = ['/login', '/register', '/login-2fa', '/share/'];

function isPublicPath(pathname: string): boolean {
  if (pathname === '/') {
    return true;
  }
  return PUBLIC_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const saved = window.localStorage.getItem('securedrop_sidebar_collapsed');
    if (saved === '1') {
      setSidebarCollapsed(true);
    }
  }, []);

  const role = useMemo(() => getCurrentUserRole(), [pathname]);
  const isPublic = isPublicPath(pathname);

  async function onLogout() {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      await logout(refreshToken);
    }
    clearPending2FA();
    clearToken();
    router.push('/login');
  }

  function onToggleSidebarCollapsed() {
    setSidebarCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem('securedrop_sidebar_collapsed', next ? '1' : '0');
      return next;
    });
  }

  if (!mounted || isPublic) {
    return <>{children}</>;
  }

  const hasToken = Boolean(getToken());
  if (!hasToken) {
    return <>{children}</>;
  }

  const navItems: NavItem[] = [
    {
      href: '/dashboard',
      label: 'Dashboard',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5" aria-hidden="true">
          <path d="M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z" />
        </svg>
      ),
    },
    {
      href: '/shared-files',
      label: 'Shared Files',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5" aria-hidden="true">
          <path d="M8 11a4 4 0 1 1 7.6 1.8L10.8 17.6a3 3 0 1 1-4.2-4.2l4.4-4.4" />
          <path d="M16 13a4 4 0 1 1-7.6-1.8L13.2 6.4a3 3 0 1 1 4.2 4.2L13 15" />
        </svg>
      ),
    },
    {
      href: '/activity',
      label: 'Activity',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5" aria-hidden="true">
          <path d="M4 12h4l2.2-5 3.6 10L16 12h4" />
        </svg>
      ),
    },
    {
      href: '/setup-2fa',
      label: 'Security (2FA)',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5" aria-hidden="true">
          <path d="M12 3 5 6v6c0 4.7 3 8.2 7 9 4-0.8 7-4.3 7-9V6z" />
          <path d="m9.5 12 2 2 3-3" />
        </svg>
      ),
    },
  ];

  const adminItems: NavItem[] = [
    {
      href: '/admin/audit',
      label: 'Admin Audit',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5" aria-hidden="true">
          <path d="M5 4h10l4 4v12H5z" />
          <path d="M9 13h6M9 17h6M15 4v4h4" />
        </svg>
      ),
    },
  ];

  return (
    <div className="h-dvh w-full overflow-hidden bg-[#EEF5F9] text-[#0C4763]">
      <header className="sticky top-0 z-30 border-b border-[#D6E4EE] bg-white/95 backdrop-blur">
        <div className="flex h-16 items-center justify-between px-4 md:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded-lg border border-[#C7DAE8] px-3 py-2 text-sm font-semibold text-[#0C4763] md:hidden"
              onClick={() => setSidebarOpen((current) => !current)}
            >
              Menu
            </button>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#3D92CB]">SecureDrop</p>
              <h1 className="text-base font-semibold">Professional Control Center</h1>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded-lg bg-[#0C4763] px-4 py-2 text-sm font-semibold text-white"
              onClick={() => void onLogout()}
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="flex h-[calc(100dvh-4rem)] gap-4 px-4 py-4 md:px-6">
        <aside
          className={`
            ${sidebarOpen ? 'block' : 'hidden'}
            h-full w-full overflow-y-auto rounded-2xl border border-[#D6E4EE] bg-white p-4 shadow-[0_12px_30px_rgba(12,71,99,0.08)]
            md:block md:shrink-0 ${sidebarCollapsed ? 'md:w-20' : 'md:w-72'}
          `}
        >
          <div className={`mb-2 flex items-center ${sidebarCollapsed ? 'justify-center' : 'justify-between'} gap-2`}>
            {!sidebarCollapsed ? (
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6A879B]">Navigation</p>
            ) : null}
            <button
              type="button"
              className="hidden rounded-lg border border-[#C7DAE8] p-2 text-[#0C4763] transition hover:bg-[#F0F6FB] md:inline-flex"
              onClick={onToggleSidebarCollapsed}
              title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {sidebarCollapsed ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5" aria-hidden="true">
                  <path d="M8 5v14M16 8l3 4-3 4M5 12h11" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5" aria-hidden="true">
                  <path d="M16 5v14M8 8l-3 4 3 4M19 12H8" />
                </svg>
              )}
            </button>
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center ${sidebarCollapsed ? 'justify-center' : 'justify-start'} gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
                    active
                      ? 'bg-[#0C4763] text-white'
                      : 'text-[#0C4763] hover:bg-[#F0F6FB]'
                  }`}
                  onClick={() => setSidebarOpen(false)}
                  title={item.label}
                >
                  <span className="shrink-0">{item.icon}</span>
                  {!sidebarCollapsed ? <span>{item.label}</span> : null}
                </Link>
              );
            })}
          </nav>

          {role === 'admin' ? (
            <>
              {!sidebarCollapsed ? (
                <p className="mb-2 mt-5 text-xs font-semibold uppercase tracking-[0.2em] text-[#6A879B]">Admin</p>
              ) : null}
              <nav className="space-y-1">
                {adminItems.map((item) => {
                  const active = pathname === item.href;
                  return (
                    <div key={item.href}>
                      <Link
                        href={item.href}
                        className={`flex items-center ${sidebarCollapsed ? 'justify-center' : 'justify-start'} gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
                          active
                            ? 'bg-[#6DBB48] text-[#07361D]'
                            : 'text-[#0C4763] hover:bg-[#ECF8E6]'
                        }`}
                        onClick={() => setSidebarOpen(false)}
                        title={item.label}
                      >
                        <span className="shrink-0">{item.icon}</span>
                        {!sidebarCollapsed ? <span>{item.label}</span> : null}
                      </Link>

                      {!sidebarCollapsed && pathname === '/admin/audit' ? (
                        <div className="ml-8 mt-1 space-y-1 border-l border-[#DCE8EF] pl-3 text-xs">
                          <Link
                            href="/admin/audit#logs-section"
                            className="block rounded-md px-2 py-1 text-[#4E6E83] transition hover:bg-[#F2F8FC] hover:text-[#0C4763]"
                            onClick={() => setSidebarOpen(false)}
                          >
                            Logs Section
                          </Link>
                          <Link
                            href="/admin/audit#user-management-section"
                            className="block rounded-md px-2 py-1 text-[#4E6E83] transition hover:bg-[#F2F8FC] hover:text-[#0C4763]"
                            onClick={() => setSidebarOpen(false)}
                          >
                            User Management
                          </Link>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </nav>
            </>
          ) : null}
        </aside>

        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
