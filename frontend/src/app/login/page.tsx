'use client';

import { useState, FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { login, ApiError } from '@/lib/api';
import { setToken, setApiKey, setOrgId } from '@/lib/auth';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await login(email, password);
      setToken(data.access_token);
      setApiKey(data.api_key);
      setOrgId(data.org_id);
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Analytics Platform</h1>
          <p className="text-sm text-gray-500 mt-1">Sign in to your workspace</p>
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4">
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div>
            <label className="label" htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              className="input"
              placeholder="you@company.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div>
            <label className="label" htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="input"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>

          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>

          <p className="text-center text-sm text-gray-500">
            No account?{' '}
            <Link href="/signup" className="text-brand-600 hover:underline font-medium">
              Create one
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
