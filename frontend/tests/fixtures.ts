import type { Job, JobPage, JobQuery } from '../src/types/jobs'

export function job(overrides: Partial<Job> = {}): Job {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    type: 'download',
    status: 'queued',
    progress_percent: 0,
    current_step: null,
    attempt_count: 0,
    max_attempts: 3,
    created_at: '2026-10-03T00:00:00Z',
    started_at: null,
    heartbeat_at: null,
    completed_at: null,
    cancelled_at: null,
    cancel_requested_at: null,
    error: null,
    ...overrides,
  }
}
export function jobPage(jobs: Job[], query: JobQuery = {}): JobPage {
  const filtered = jobs.filter(
    (job) =>
      (!query.status || job.status === query.status) && (!query.type || job.type === query.type),
  )
  const size = query.page_size ?? 25
  const page = query.page ?? 1
  return {
    items: filtered.slice((page - 1) * size, page * size),
    total: filtered.length,
    page,
    page_size: size,
  }
}
