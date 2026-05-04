'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { isAuthenticated } from '@/lib/auth';
import Sidebar from './Sidebar';

/**
 * Authenticated shell: redirects to /login if no JWT,
 * otherwise renders the sidebar + main content slot.
 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/login');
    }
  }, [router]);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8 max-w-7xl">
        {children}
      </main>
    </div>
  );
}
