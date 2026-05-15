'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { isAuthenticated } from '@/lib/auth';
import Sidebar from './Sidebar';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';

interface AppShellProps {
  children: React.ReactNode;
  fullBleed?: boolean;
}

export default function AppShell({ children, fullBleed = false }: AppShellProps) {
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/login');
      return;
    }
    // Ping on every mount so Render wakes up before the user interacts.
    // Uses no-cors so it doesn't block on CORS errors — just fires and forgets.
    fetch(`${BASE}/system/health`, { mode: 'no-cors' }).catch(() => {});
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
