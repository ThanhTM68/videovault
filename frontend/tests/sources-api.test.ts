import { afterEach, expect, it, vi } from 'vitest'
import { resolveSource, submitBatch } from '../src/api/sources'
const criteria = { url: 'https://youtube.com/@research', n: 1, ordering: 'source' as const }
const response = {
  preview_id: 'fixture-preview-0000000000000',
  ordering: 'source',
  source: {
    platform: 'youtube',
    source_type: 'channel_videos',
    source_id: null,
    display_name: null,
    canonical_url: criteria.url + '/videos',
    total_available: null,
    capabilities: {
      list_profile_or_channel: true,
      sort_newest: false,
      sort_oldest: false,
      sort_views: false,
      filter_views: false,
      filter_date: false,
      filter_duration: true,
    },
  },
  candidates: [
    {
      platform: 'youtube',
      platform_video_id: 'clip0000001',
      canonical_url: 'https://www.youtube.com/watch?v=clip0000001',
      title: null,
      creator: null,
      thumbnail_url: null,
      duration_seconds: null,
      upload_date: null,
      view_count: null,
      has_download_history: false,
      has_file: false,
    },
  ],
  statistics: {
    enumerated_count: 1,
    rejected_count: 0,
    duplicate_count: 0,
    metadata_unavailable_count: 0,
    filtered_count: 0,
    returned_count: 1,
    already_downloaded_count: 0,
    scan_limit: 100,
  },
}
const batchBody = {
  preview_id: response.preview_id,
  selected_ids: ['clip0000001'],
  max_height: 1080 as const,
  preferred_container: 'mp4' as const,
  audio_enabled: true,
}
const result = {
  jobs: [{ id: 'job-id', status: 'queued' }],
  outcomes: [{ platform_video_id: 'clip0000001', outcome: 'queued', job_id: 'job-id' }],
  requested_count: 1,
  created_count: 1,
  skipped_history_count: 0,
  skipped_duplicate_selection_count: 0,
}
function fakeResponse(data: unknown, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(data), { status })),
  )
}
afterEach(() => vi.unstubAllGlobals())
it('posts typed metadata-only preview and ordinary job selection bodies', async () => {
  fakeResponse(response)
  expect(await resolveSource(criteria)).toEqual(response)
  expect(fetch).toHaveBeenCalledWith(
    '/api/v1/sources/resolve',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify(criteria),
      signal: expect.any(AbortSignal),
    }),
  )
  fakeResponse(result, 202)
  expect(await submitBatch(batchBody)).toEqual(result)
  expect(fetch).toHaveBeenCalledWith(
    '/api/v1/sources/batch-download',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify(batchBody),
    }),
  )
})
it.each([
  { ...response, source: { ...response.source, capabilities: {} } },
  { ...response, statistics: { ...response.statistics, returned_count: 0 } },
  { ...response, candidates: [{ ...response.candidates[0], has_download_history: undefined }] },
  { ...response, candidates: [{ ...response.candidates[0], view_count: -1 }] },
  { ...response, candidates: [{ ...response.candidates[0], platform: 'facebook' }] },
  { ...response, ordering: 'imaginary' },
])('rejects malformed preview responses', async (data) => {
  fakeResponse(data)
  await expect(resolveSource(criteria)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
})
it.each([
  { ...result, created_count: 2 },
  { ...result, outcomes: [] },
  { ...result, jobs: [{ id: 'job-id', status: 'completed' }] },
  { ...result, outcomes: [{ ...result.outcomes[0], job_id: null }] },
])('rejects fabricated or inconsistent submission counts/state', async (data) => {
  fakeResponse(data, 202)
  await expect(submitBatch(batchBody)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
})
it('preserves stable backend capability errors', async () => {
  fakeResponse(
    { error: { code: 'SOURCE_SORT_UNSUPPORTED', message: 'Ordering unsupported', details: {} } },
    400,
  )
  await expect(resolveSource(criteria)).rejects.toMatchObject({
    code: 'SOURCE_SORT_UNSUPPORTED',
    status: 400,
  })
})
