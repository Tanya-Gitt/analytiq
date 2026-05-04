'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { isAuthenticated } from '@/lib/auth';

/**
 * Root page: redirect to /dashboard if logged in, else /login.
 */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace(isAuthenticated() ? '/dashboard' : '/login');
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="animate-pulse text-gray-400">Loading…</div>
    </div>
  );
}
