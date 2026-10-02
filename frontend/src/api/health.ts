import type { HealthResponse } from '../types/api'

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/v1/health', {
    signal: AbortSignal.timeout(5000),
  })
  if (!response.ok) {
    throw new Error('Backend health request failed')
  }
  const data: unknown = await response.json()
  if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
    throw new Error('Unexpected health response')
  }
  return { status: 'ok' }
}
