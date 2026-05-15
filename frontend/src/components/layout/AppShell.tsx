'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { isAuthenticated } from '@/lib/auth';
import Sidebar from './Sidebar';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';

/**
 * Authenticated shell: redirects to /login if no JWT,
 * otherwise renders the sidebar + main content slot.
 */
interface AppShellProps {
  children: React.ReactNode;
  /** Remove padding and let the page manage its own scroll — use for full-height UIs like chat. */
  fullBleed?: boolean;
}

// Fire once per browser session to wake the Render free-tier backend from sleep.
const _woken = { current: false };

export default function AppShell({ children, fullBleed = false }: AppShellProps) {
  const router = useRouter();
  const didPing = useRef(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/login');
      return;
    }
    // Silent wake-up ping — Render free-tier sleeps after 15 min inactivity.
    // This fires once per session so the backend is warm before the user clicks anything.
    if (!_woken.current && !didPing.current) {
      _woken.current = true;
      didPing.current = true;
      fetch(`${BASE}/system/health`).catch(() => {/* ignore */});
    }
  }, [router]);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className={fullBleed
        ? 'flex-1 overflow-hidden flex flex-col'
        : 'flex-1 overflow-y-auto p-8 max-w-7xl'
      }>
        {children}
      </main>
    </div>
  );
}
