import type { QueueState } from '../types/api'
import { isRecord, request } from './client'

const isQueueState = (data: unknown): data is QueueState =>
  isRecord(data) && typeof data.paused === 'boolean'
export const fetchQueueState = (signal?: AbortSignal): Promise<QueueState> =>
  request('/queue', isQueueState, { signal })
export const pauseQueue = (): Promise<QueueState> =>
  request('/queue/pause', isQueueState, { method: 'POST' })
export const resumeQueue = (): Promise<QueueState> =>
  request('/queue/resume', isQueueState, { method: 'POST' })
