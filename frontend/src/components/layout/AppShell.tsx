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
    // Ping immediately on mount, then every 4 minutes to prevent Render free-tier sleep.
    const ping = () => fetch(`${BASE}/system/health`, { mode: 'no-cors' }).catch(() => {});
    ping();
    const id = setInterval(ping, 4 * 60 * 1000);
    return () => clearInterval(id);
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
