'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { isAuthenticated } from '@/lib/auth';
import Sidebar from './Sidebar';

/**
 * Authenticated shell: redirects to /login if no JWT,
 * otherwise renders the sidebar + main content slot.
 */
interface AppShellProps {
  children: React.ReactNode;
  /** Remove padding and let the page manage its own scroll — use for full-height UIs like chat. */
  fullBleed?: boolean;
}

export default function AppShell({ children, fullBleed = false }: AppShellProps) {
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/login');
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
