export const JOB_STATUSES = [
  'queued',
  'resolving',
  'downloading',
  'processing',
  'uploading',
  'completed',
  'failed',
  'cancelled',
  'skipped_duplicate',
] as const
export type JobStatus = (typeof JOB_STATUSES)[number]

export interface Job {
  id: string
  type: string
  status: JobStatus
  progress_percent: number | null
  current_step: string | null
  attempt_count: number
  max_attempts: number
  created_at: string
  started_at: string | null
  heartbeat_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  cancel_requested_at: string | null
  error: { code: string; message: string } | null
}

export interface JobPage {
  items: Job[]
  page: number
  page_size: number
  total: number
}
export interface JobQuery {
  page?: number
  page_size?: number
  status?: JobStatus
  type?: string
}
export interface QueueCounts {
  queued: number
  running: number
  completed: number
  failed: number
}
