export interface HealthResponse {
  status: 'ok'
}

export interface ApiErrorEnvelope {
  error: { code: string; message: string; details: Record<string, unknown> }
}

export interface DownloadSubmissionRequest {
  urls: string[]
  max_height: 1080 | 720 | 480
  preferred_container: 'mp4' | 'mkv' | 'webm'
  audio_enabled: boolean
  force?: boolean
  storage_target?: import('./storage').StorageProvider
}

export interface DownloadSubmissionResponse {
  jobs: { id: string; status: 'queued' }[]
}

export interface QueueState {
  paused: boolean
}

export interface VideoPreview {
  platform: 'youtube' | 'tiktok' | 'douyin' | 'instagram' | 'facebook'
  platform_video_id: string
  canonical_url: string
  title: string | null
  creator: string | null
  duration_seconds: number | null
  width: number | null
  height: number | null
  thumbnail_url: string | null
  video_id?: string | null
  has_file?: boolean
  has_download_history?: boolean
}
