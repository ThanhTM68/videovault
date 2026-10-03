import { isRecord, nullableNumber, nullableString, request } from './client'
import { JOB_STATUSES } from '../types/jobs'
import {
  PLATFORMS,
  type LibraryVideo,
  type VideoDetail,
  type HistoryItem,
  type NamedItem,
  type Page,
  type LibraryFilters,
  type DeleteOperation,
} from '../types/library'
import type { DownloadSubmissionResponse } from '../types/api'

export const isNamed = (data: unknown): data is NamedItem =>
  isRecord(data) && typeof data.id === 'string' && typeof data.name === 'string'
export const isVideo = (data: unknown): data is LibraryVideo =>
  isRecord(data) &&
  typeof data.id === 'string' &&
  PLATFORMS.includes(data.platform as LibraryVideo['platform']) &&
  typeof data.platform_video_id === 'string' &&
  typeof data.title === 'string' &&
  nullableString(data.creator) &&
  nullableString(data.thumbnail_url) &&
  nullableString(data.upload_date) &&
  ['duration_seconds', 'view_count', 'width', 'height'].every((key) => nullableNumber(data[key])) &&
  typeof data.has_file === 'boolean' &&
  typeof data.has_download_history === 'boolean' &&
  Array.isArray(data.tags) &&
  data.tags.every(isNamed) &&
  Array.isArray(data.collections) &&
  data.collections.every(isNamed)
export const isHistory = (data: unknown): data is HistoryItem =>
  isRecord(data) &&
  ['id', 'video_id', 'title', 'requested_quality', 'created_at'].every(
    (key) => typeof data[key] === 'string',
  ) &&
  PLATFORMS.includes(data.platform as LibraryVideo['platform']) &&
  JOB_STATUSES.includes(data.status as HistoryItem['status']) &&
  typeof data.forced === 'boolean' &&
  nullableNumber(data.attempt_number) &&
  ['job_id', 'started_at', 'completed_at', 'failure_code', 'failure_message'].every((key) =>
    nullableString(data[key]),
  )
export const isDetail = (data: unknown): data is VideoDetail =>
  isVideo(data) &&
  isRecord(data) &&
  typeof data.description === 'string' &&
  Array.isArray(data.history) &&
  data.history.every(isHistory) &&
  Array.isArray(data.files) &&
  data.files.every(
    (file) =>
      isRecord(file) &&
      typeof file.id === 'string' &&
      typeof file.size_bytes === 'number' &&
      file.size_bytes >= 0 &&
      nullableString(file.sha256) &&
      typeof file.container === 'string' &&
      nullableNumber(file.width) &&
      nullableNumber(file.height) &&
      ['available', 'missing', 'deleted', 'unavailable'].includes(String(file.state)),
  )
function isPage<T>(guard: (value: unknown) => value is T): (value: unknown) => value is Page<T> {
  return (data): data is Page<T> =>
    isRecord(data) &&
    Array.isArray(data.items) &&
    data.items.every(guard) &&
    ['page', 'page_size', 'total'].every((key) => Number.isInteger(data[key])) &&
    Number(data.page) >= 1 &&
    Number(data.page_size) >= 1 &&
    Number(data.page_size) <= 100 &&
    Number(data.total) >= 0
}
function query(values: Record<string, string | number | boolean | undefined>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values))
    if (value !== undefined && value !== '') params.set(key, String(value))
  return params.toString()
}
export const fetchLibrary = (
  filters: LibraryFilters,
  page = 1,
  signal?: AbortSignal,
): Promise<Page<LibraryVideo>> =>
  request('/videos?' + query({ ...filters, page, page_size: 25 }), isPage(isVideo), { signal })
export const fetchDetail = (id: string, signal?: AbortSignal): Promise<VideoDetail> =>
  request('/videos/' + encodeURIComponent(id), isDetail, { signal })
export const destroyVideo = (id: string, action: DeleteOperation): Promise<VideoDetail> =>
  request(`/videos/${encodeURIComponent(id)}/${action}`, isDetail, { method: 'DELETE' })
export const forceRedownload = (id: string): Promise<DownloadSubmissionResponse> =>
  request(
    `/videos/${encodeURIComponent(id)}/redownload`,
    (data): data is DownloadSubmissionResponse =>
      isRecord(data) &&
      Array.isArray(data.jobs) &&
      data.jobs.length > 0 &&
      data.jobs.every(
        (job) => isRecord(job) && typeof job.id === 'string' && job.status === 'queued',
      ),
    { method: 'POST' },
  )
export const fetchHistory = (
  page = 1,
  filters: { platform?: LibraryVideo['platform']; status?: HistoryItem['status'] } = {},
  signal?: AbortSignal,
): Promise<Page<HistoryItem>> =>
  request('/history?' + query({ ...filters, page, page_size: 25 }), isPage(isHistory), { signal })
export const fetchNamed = (kind: 'tags' | 'collections'): Promise<NamedItem[]> =>
  request('/' + kind, (data): data is NamedItem[] => Array.isArray(data) && data.every(isNamed))
export const createNamed = (kind: 'tags' | 'collections', name: string): Promise<NamedItem> =>
  request('/' + kind, isNamed, { method: 'POST', body: { name } })
export const attachNamed = (
  kind: 'tags' | 'collections',
  videoId: string,
  itemId: string,
  remove = false,
): Promise<VideoDetail> =>
  request(
    kind === 'tags'
      ? `/videos/${encodeURIComponent(videoId)}/tags/${encodeURIComponent(itemId)}`
      : `/collections/${encodeURIComponent(itemId)}/videos/${encodeURIComponent(videoId)}`,
    isDetail,
    { method: remove ? 'DELETE' : 'POST' },
  )
