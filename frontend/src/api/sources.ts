import type { BatchRequest, BatchResult, SourcePreview, SourceRequest } from '../types/sources'
import { isRecord, nullableNumber, nullableString, request } from './client'

const platforms = ['youtube', 'tiktok', 'douyin', 'instagram', 'facebook']
const orders = ['source', 'newest', 'oldest', 'views']
const boundedCount = (v: unknown): v is number =>
  typeof v === 'number' && Number.isInteger(v) && v >= 0 && v <= 100
const nonnegative = (v: unknown) => nullableNumber(v) && (v === null || v >= 0)
const caps = [
  'list_profile_or_channel',
  'sort_newest',
  'sort_oldest',
  'sort_views',
  'filter_views',
  'filter_date',
  'filter_duration',
]
function isPreview(data: unknown): data is SourcePreview {
  if (!isRecord(data) || !isRecord(data.source) || !isRecord(data.statistics)) return false
  const source = data.source,
    stats = data.statistics
  return (
    typeof data.preview_id === 'string' &&
    data.preview_id.length >= 16 &&
    typeof data.ordering === 'string' &&
    orders.includes(data.ordering) &&
    typeof source.platform === 'string' &&
    platforms.includes(source.platform) &&
    source.source_type === 'channel_videos' &&
    nullableString(source.source_id) &&
    nullableString(source.display_name) &&
    typeof source.canonical_url === 'string' &&
    nonnegative(source.total_available) &&
    isRecord(source.capabilities) &&
    caps.every(
      (key) => typeof (source.capabilities as Record<string, unknown>)[key] === 'boolean',
    ) &&
    [
      'enumerated_count',
      'rejected_count',
      'duplicate_count',
      'metadata_unavailable_count',
      'filtered_count',
      'returned_count',
      'already_downloaded_count',
      'scan_limit',
    ].every((key) => boundedCount(stats[key])) &&
    Array.isArray(data.candidates) &&
    data.candidates.length <= 100 &&
    data.candidates.length === stats.returned_count &&
    data.candidates.every(
      (item) =>
        isRecord(item) &&
        item.platform === source.platform &&
        typeof item.platform_video_id === 'string' &&
        typeof item.canonical_url === 'string' &&
        nullableString(item.title) &&
        nullableString(item.creator) &&
        nullableString(item.thumbnail_url) &&
        nonnegative(item.duration_seconds) &&
        nullableString(item.upload_date) &&
        nonnegative(item.view_count) &&
        typeof item.has_download_history === 'boolean' &&
        typeof item.has_file === 'boolean',
    )
  )
}
function isResult(data: unknown): data is BatchResult {
  if (!isRecord(data) || !Array.isArray(data.jobs) || !Array.isArray(data.outcomes)) return false
  return (
    [
      'requested_count',
      'created_count',
      'skipped_history_count',
      'skipped_duplicate_selection_count',
    ].every((key) => boundedCount(data[key])) &&
    data.jobs.length === data.created_count &&
    data.outcomes.length === data.requested_count &&
    (data.created_count as number) +
      (data.skipped_history_count as number) +
      (data.skipped_duplicate_selection_count as number) ===
      data.requested_count &&
    data.jobs.every(
      (job) => isRecord(job) && typeof job.id === 'string' && job.status === 'queued',
    ) &&
    data.outcomes.every(
      (item) =>
        isRecord(item) &&
        typeof item.platform_video_id === 'string' &&
        ['queued', 'skipped_history', 'skipped_duplicate_selection'].includes(
          String(item.outcome),
        ) &&
        (item.outcome === 'queued' ? typeof item.job_id === 'string' : item.job_id === null),
    )
  )
}
export const resolveSource = (body: SourceRequest, signal?: AbortSignal): Promise<SourcePreview> =>
  request('/sources/resolve', isPreview, { method: 'POST', body, signal, timeout: 130000 })
export const submitBatch = (body: BatchRequest): Promise<BatchResult> =>
  request('/sources/batch-download', isResult, { method: 'POST', body })
