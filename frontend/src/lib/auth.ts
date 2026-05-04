/**
 * Client-side auth helpers.
 * JWT is stored in localStorage (SPA pattern).
 * For a production deployment, prefer httpOnly cookies.
 */

const TOKEN_KEY = 'analytics_jwt';
const API_KEY_KEY = 'analytics_api_key';
const ORG_ID_KEY = 'analytics_org_id';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getApiKey(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(API_KEY_KEY);
}

export function setApiKey(apiKey: string): void {
  localStorage.setItem(API_KEY_KEY, apiKey);
}

export function getOrgId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ORG_ID_KEY);
}

export function setOrgId(orgId: string): void {
  localStorage.setItem(ORG_ID_KEY, orgId);
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(API_KEY_KEY);
  localStorage.removeItem(ORG_ID_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

/** Return auth header for fetch calls. */
export function authHeader(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
