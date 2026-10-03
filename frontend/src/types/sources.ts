import type { DownloadOptions, DownloadSubmissionResponse, VideoPreview } from './api'

export type SourceOrdering = 'source' | 'newest' | 'oldest' | 'views'
export interface SourceRequest {
  url: string
  n: number
  ordering: SourceOrdering
  min_views?: number
  max_views?: number
  date_from?: string
  date_to?: string
  min_duration?: number
  max_duration?: number
}
export interface SourceCapabilities {
  list_profile_or_channel: boolean
  sort_newest: boolean
  sort_oldest: boolean
  sort_views: boolean
  filter_views: boolean
  filter_date: boolean
  filter_duration: boolean
}
export interface BatchCandidate {
  platform: VideoPreview['platform']
  platform_video_id: string
  canonical_url: string
  title: string | null
  creator: string | null
  thumbnail_url: string | null
  duration_seconds: number | null
  upload_date: string | null
  view_count: number | null
  has_download_history: boolean
  has_file: boolean
}
export interface SourcePreview {
  preview_id: string
  source: {
    platform: VideoPreview['platform']
    source_type: 'channel_videos'
    source_id: string | null
    display_name: string | null
    canonical_url: string
    capabilities: SourceCapabilities
    total_available: number | null
  }
  candidates: BatchCandidate[]
  statistics: {
    enumerated_count: number
    rejected_count: number
    duplicate_count: number
    metadata_unavailable_count: number
    filtered_count: number
    returned_count: number
    already_downloaded_count: number
    scan_limit: number
  }
  ordering: SourceOrdering
}
export interface BatchRequest extends DownloadOptions {
  preview_id: string
  selected_ids: string[]
}
export interface BatchResult extends DownloadSubmissionResponse {
  outcomes: {
    platform_video_id: string
    outcome: 'queued' | 'skipped_history' | 'skipped_duplicate_selection'
    job_id: string | null
  }[]
  requested_count: number
  created_count: number
  skipped_history_count: number
  skipped_duplicate_selection_count: number
}
