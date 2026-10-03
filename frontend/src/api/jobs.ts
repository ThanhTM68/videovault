import type { Job, JobPage, JobQuery } from '../types/jobs'
import { JOB_STATUSES } from '../types/jobs'
import { isRecord, nullableString, request } from './client'

export function isJob(data: unknown): data is Job {
  return (
    isRecord(data) &&
    typeof data.id === 'string' &&
    typeof data.type === 'string' &&
    JOB_STATUSES.some((status) => status === data.status) &&
    (data.progress_percent === null ||
      (typeof data.progress_percent === 'number' &&
        Number.isFinite(data.progress_percent) &&
        data.progress_percent >= 0 &&
        data.progress_percent <= 100)) &&
    nullableString(data.current_step) &&
    typeof data.created_at === 'string' &&
    ['started_at', 'heartbeat_at', 'completed_at', 'cancelled_at', 'cancel_requested_at'].every(
      (key) => nullableString(data[key]),
    ) &&
    Number.isInteger(data.attempt_count) &&
    Number(data.attempt_count) >= 0 &&
    Number.isInteger(data.max_attempts) &&
    Number(data.max_attempts) >= 1 &&
    (data.error === null ||
      (isRecord(data.error) &&
        typeof data.error.code === 'string' &&
        typeof data.error.message === 'string'))
  )
}

export function fetchJobs(query: JobQuery = {}, signal?: AbortSignal): Promise<JobPage> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query))
    if (value !== undefined) params.set(key, String(value))
  return request(
    `/jobs?${params}`,
    (data): data is JobPage =>
      isRecord(data) &&
      Array.isArray(data.items) &&
      data.items.every(isJob) &&
      Number.isInteger(data.total) &&
      Number(data.total) >= 0 &&
      Number.isInteger(data.page) &&
      Number(data.page) >= 1 &&
      Number.isInteger(data.page_size) &&
      Number(data.page_size) >= 1,
    { signal },
  )
}

export const fetchJob = (id: string, signal?: AbortSignal): Promise<Job> =>
  request(`/jobs/${encodeURIComponent(id)}`, isJob, { signal })
export const cancelJob = (id: string): Promise<Job> =>
  request(`/jobs/${encodeURIComponent(id)}/cancel`, isJob, { method: 'POST' })
export const retryJob = (id: string): Promise<Job> =>
  request(`/jobs/${encodeURIComponent(id)}/retry`, isJob, { method: 'POST' })
