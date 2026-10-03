import type {
  DownloadSubmissionRequest,
  DownloadSubmissionResponse,
  VideoPreview,
} from '../types/api'
import { isRecord, nullableNumber, nullableString, request } from './client'

export const submitDownloads = (
  body: DownloadSubmissionRequest,
): Promise<DownloadSubmissionResponse> =>
  request(
    '/downloads',
    (data): data is DownloadSubmissionResponse =>
      isRecord(data) &&
      Array.isArray(data.jobs) &&
      data.jobs.length > 0 &&
      data.jobs.every(
        (job) => isRecord(job) && typeof job.id === 'string' && job.status === 'queued',
      ),
    { method: 'POST', body },
  )

export function resolvePreview(url: string, signal?: AbortSignal): Promise<VideoPreview> {
  return request(
    '/videos/resolve',
    (data): data is VideoPreview =>
      isRecord(data) &&
      ['youtube', 'tiktok', 'douyin', 'instagram', 'facebook'].includes(String(data.platform)) &&
      typeof data.platform_video_id === 'string' &&
      typeof data.canonical_url === 'string' &&
      nullableString(data.title) &&
      nullableString(data.creator) &&
      nullableString(data.thumbnail_url) &&
      nullableNumber(data.duration_seconds) &&
      nullableNumber(data.width) &&
      nullableNumber(data.height) &&
      (data.video_id === undefined || nullableString(data.video_id)) &&
      (data.has_file === undefined || typeof data.has_file === 'boolean') &&
      (data.has_download_history === undefined || typeof data.has_download_history === 'boolean'),
    { method: 'POST', body: { url }, signal, timeout: 35000 },
  )
}
