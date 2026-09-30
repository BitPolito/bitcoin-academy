// Derive the service root (no /api suffix) from the same env vars used elsewhere.
const SERVICE_ROOT =
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/api$/, '')
    : 'http://localhost:8000');

export interface HealthStatus {
  status: 'healthy' | 'degraded';
  database: 'connected' | 'disconnected' | 'unknown';
  qvac: 'connected' | 'unreachable' | 'unknown';
  cache: 'redis' | 'in-memory' | 'unknown';
}

export async function fetchHealthStatus(): Promise<HealthStatus> {
  const res = await fetch(`${SERVICE_ROOT}/health`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json() as Promise<HealthStatus>;
}
