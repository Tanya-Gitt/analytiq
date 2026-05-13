'use client';

/**
 * SSO Success landing page.
 *
 * The backend redirects here after a successful OAuth callback:
 *   /auth/sso-success?token=<jwt>&org_id=<uuid>
 *
 * This page reads those query params, stores them in localStorage
 * (same as the normal login flow), then redirects to /dashboard.
 * It never renders visible content — it's purely a token handoff.
 */

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { setToken, setOrgId } from '@/lib/auth';

function SSOSuccessInner() {
  const router       = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const token  = searchParams.get('token');
    const org_id = searchParams.get('org_id');

    if (!token || !org_id) {
      router.replace('/login?error=missing_token');
      return;
    }

    setToken(token);
    setOrgId(org_id);
    // api_key is not available from SSO (no separate api_key in response).
    // The settings page fetches it via /api/auth/me when needed.
    const next = searchParams.get('next') ?? '/dashboard';
    router.replace(next.startsWith('/') ? next : '/dashboard');
  }, [router, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center space-y-3">
        <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-gray-500">Completing sign-in…</p>
      </div>
    </div>
  );
}

export default function SSOSuccessPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      <SSOSuccessInner />
    </Suspense>
  );
}
