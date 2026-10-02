import type { Job, JobStatus } from '../types/jobs'

export const ACTIVE_STATUSES: ReadonlySet<JobStatus> = new Set([
  'resolving',
  'downloading',
  'processing',
  'uploading',
])
export const isActive = (status: JobStatus): boolean => ACTIVE_STATUSES.has(status)
export const canCancel = (job: Job): boolean =>
  (job.status === 'queued' || isActive(job.status)) && !job.cancel_requested_at
export const canRetry = (job: Job): boolean =>
  job.status === 'failed' && job.attempt_count < job.max_attempts
export const STATUS_LABELS: Record<JobStatus, string> = {
  queued: 'Queued',
  resolving: 'Resolving',
  downloading: 'Downloading',
  processing: 'Processing',
  uploading: 'Uploading',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  skipped_duplicate: 'Skipped duplicate',
}
export function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '—'
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}
export function stepLabel(step: string | null): string {
  return step
    ? step.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
    : 'Waiting to start'
}
