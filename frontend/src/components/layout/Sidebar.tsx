'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { clearAuth } from '@/lib/auth';
import clsx from 'clsx';
import ConfirmDialog from '@/components/ConfirmDialog';

const SCROLL_KEY = 'sidebar-scroll-pos';

// ── Icon helper ───────────────────────────────────────────────────────────────
function Icon({ d }: { d: string }) {
  return (
    <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

// ── Nav structure ─────────────────────────────────────────────────────────────
const SECTIONS = [
  {
    label: 'Analytics',
    items: [
      { href: '/dashboard',     label: 'Dashboard',    d: 'M3 3h7v7H3V3zm0 11h7v7H3v-7zm11-11h7v7h-7V3zm0 11h7v7h-7v-7z' },
      { href: '/live',          label: 'Live Feed',    d: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z' },
      { href: '/live/debugger', label: 'Debugger',     d: 'M12 12.75c1.148 0 2.278.08 3.383.237 1.037.146 1.866.966 1.866 2.013 0 3.728-2.35 6.75-5.25 6.75S6.75 18.728 6.75 15c0-1.046.83-1.867 1.866-2.013A24.204 24.204 0 0112 12.75zm0 0c2.883 0 5.647.508 8.207 1.44a23.91 23.91 0 01-1.152 6.06M12 12.75c-2.883 0-5.647.508-8.208 1.44.165 2.104.95 4.14 2.116 5.821M12 12.75V3m0 0L8.25 6.75M12 3l3.75 3.75' },
      { href: '/people',        label: 'People',       d: 'M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z' },
      { href: '/funnels',       label: 'Funnels',      d: 'M3 4h18l-7 8v5l-4 3V12L3 4z' },
      { href: '/retention',     label: 'Retention',    d: 'M3 3h7v7H3V3zm0 11h7v7H3v-7zm11-11h7v7h-7V3zm0 11h7v7h-7v-7z' },
      { href: '/paths',         label: 'Path Analysis',d: 'M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5' },
    ],
  },
  {
    label: 'Product',
    items: [
      { href: '/flags',     label: 'Feature Flags', d: 'M3 3v18M3 6l9-3 9 3v9l-9 3-9-3V6z' },
      { href: '/anomalies', label: 'Anomalies',     d: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z' },
      { href: '/copilot',   label: 'AI Copilot',   d: 'M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z' },
      { href: '/heatmaps',  label: 'Heatmaps',     d: 'M15.182 15.182a4.5 4.5 0 01-6.364 0M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
      { href: '/churn',     label: 'Churn',         d: 'M2.25 6L9 12.75l4.286-4.286a11.948 11.948 0 014.306 6.43l.776 2.898m0 0l3.182-5.511m-3.182 5.51l-5.511-3.181' },
    ],
  },
  {
    label: 'Data',
    items: [
      { href: '/connectors', label: 'Connectors',      d: 'M13 10V3L4 14h7v7l9-11h-7z' },
      { href: '/setup',      label: 'SDK Setup',        d: 'M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5' },
      { href: '/warehouse',  label: 'Warehouse',        d: 'M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375' },
      { href: '/storage',    label: 'Storage',          d: 'M3 5a2 2 0 012-2h14a2 2 0 012 2v2a2 2 0 01-2 2H5a2 2 0 01-2-2V5zm0 7a2 2 0 012-2h14a2 2 0 012 2v2a2 2 0 01-2 2H5a2 2 0 01-2-2v-2z' },
      { href: '/schema',     label: 'Schema Registry',  d: 'M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z' },
    ],
  },
  {
    label: 'Admin',
    items: [
      { href: '/api-keys', label: 'API Keys',    d: 'M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z' },
      { href: '/reports',  label: 'Reports',     d: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z' },
      { href: '/embed',    label: 'Embed',       d: 'M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25' },
      { href: '/system',   label: 'System',      d: 'M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3' },
      { href: '/alerts',   label: 'Alerts',      d: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9' },
      { href: '/gdpr',     label: 'GDPR / CCPA', d: 'M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z' },
      { href: '/audit',    label: 'Audit Log',   d: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
      { href: '/settings', label: 'Settings',    d: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router   = useRouter();
  const navRef   = useRef<HTMLElement>(null);
  const [logoutOpen, setLogoutOpen] = useState(false);

  // Restore scroll on every mount (component remounts on each page navigation)
  useEffect(() => {
    const saved = sessionStorage.getItem(SCROLL_KEY);
    if (saved && navRef.current) {
      navRef.current.scrollTop = Number(saved);
    }
  }, []);

  // Save scroll before each navigation click
  function saveScroll() {
    if (navRef.current) {
      sessionStorage.setItem(SCROLL_KEY, String(navRef.current.scrollTop));
    }
  }

  function doLogout() {
    clearAuth();
    router.push('/login');
  }

  return (
    <aside className="w-52 flex-shrink-0 border-r border-gray-200 bg-white flex flex-col h-screen sticky top-0">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-gray-100">
        <span className="font-bold text-base text-brand-600 tracking-tight">
          Analytiq
        </span>
      </div>

      {/* Nav — scrollable, remembers position across navigations */}
      <nav ref={navRef} className="flex-1 px-2 py-3 overflow-y-auto" style={{ scrollbarWidth: 'thin' }}>
        {SECTIONS.map(section => (
          <div key={section.label} className="mb-4">
            <p className="px-3 mb-1 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
              {section.label}
            </p>
            <div className="space-y-0.5">
              {section.items.map(item => {
                const active = item.href === '/live'
                  ? pathname === '/live' || pathname === '/live/'
                  : pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={saveScroll}
                    className={clsx(
                      'flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                      active
                        ? 'bg-brand-50 text-brand-700'
                        : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
                    )}
                  >
                    <Icon d={item.d} />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Logout */}
      <div className="px-2 py-3 border-t border-gray-100">
        <button
          onClick={() => setLogoutOpen(true)}
          className="flex items-center gap-2.5 px-3 py-1.5 w-full rounded-lg
                     text-xs font-medium text-gray-600 hover:bg-gray-50
                     hover:text-gray-900 transition-colors"
        >
          <Icon d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          Log out
        </button>
      </div>

      <ConfirmDialog
        open={logoutOpen}
        title="Log out?"
        description="Your session will be ended. You'll need to sign in again to access the dashboard."
        confirmWord="logout"
        confirmLabel="Log out"
        onConfirm={doLogout}
        onClose={() => setLogoutOpen(false)}
      />
    </aside>
  );
}
