import type { HealthResponse } from '../types/api'
import { isRecord, request } from './client'

export async function fetchHealth(): Promise<HealthResponse> {
  return request(
    '/health',
    (data): data is HealthResponse => isRecord(data) && data.status === 'ok',
    { timeout: 5000 },
  )
}
