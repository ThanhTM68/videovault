export type Platform = 'youtube' | 'tiktok' | 'douyin' | 'instagram' | 'facebook'
export const PLATFORMS: Platform[] = ['youtube', 'tiktok', 'douyin', 'instagram', 'facebook']
export interface NamedItem {
  id: string
  name: string
}
export interface LibraryVideo {
  id: string
  platform: Platform
  platform_video_id: string
  title: string
  creator: string | null
  thumbnail_url: string | null
  duration_seconds: number | null
  upload_date: string | null
  view_count: number | null
  width: number | null
  height: number | null
  has_file: boolean
  has_download_history: boolean
  tags: NamedItem[]
  collections: NamedItem[]
}
export interface HistoryItem {
  id: string
  video_id: string
  title: string
  platform: Platform
  status: import('./jobs').JobStatus
  forced: boolean
  attempt_number: number | null
  job_id: string | null
  requested_quality: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  failure_code: string | null
  failure_message: string | null
}
export interface FileSummary {
  id: string
  storage_provider: import('./storage').StorageProvider
  file_name: string
  size_bytes: number
  sha256: string | null
  container: string
  width: number | null
  height: number | null
  state: 'available' | 'stored' | 'missing' | 'deleted' | 'unavailable'
}
export interface VideoDetail extends LibraryVideo {
  description: string
  history: HistoryItem[]
  files: FileSummary[]
}
export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}
export interface LibraryFilters {
  search?: string
  platform?: Platform
  has_file?: boolean
  has_download_history?: boolean
  tag_id?: string
  collection_id?: string
}
export type DeleteOperation = 'file' | 'history' | 'all'
