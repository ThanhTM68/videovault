import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BatchView from '../src/views/BatchView.vue'
import { useBatchStore } from '../src/stores/batch'
import { useHealthStore } from '../src/stores/health'
import * as api from '../src/api/sources'
import { ApiError } from '../src/api/client'
import type { SourcePreview, BatchResult } from '../src/types/sources'

vi.mock('../src/api/sources', () => ({ resolveSource: vi.fn(), submitBatch: vi.fn() }))
vi.mock('../src/api/storage', () => ({
  fetchStorage: vi.fn(async () => ({
    default_target: 'local',
    providers: [
      { provider: 'local', available: true },
      { provider: 'google_drive', available: true },
    ],
  })),
}))
const ids = ['clip0000001', 'clip0000002']
const criteria = { url: 'https://youtube.com/@research', n: 20, ordering: 'source' as const }
const options = {
  max_height: 1080 as const,
  preferred_container: 'mp4' as const,
  audio_enabled: true,
}
export function sourcePreview(): SourcePreview {
  return {
    preview_id: 'preview-fixture-00000000000001',
    ordering: 'source',
    source: {
      platform: 'youtube',
      source_type: 'channel_videos',
      source_id: null,
      display_name: 'Research',
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
    candidates: ids.map((id, index) => ({
      platform: 'youtube',
      platform_video_id: id,
      canonical_url: 'https://www.youtube.com/watch?v=' + id,
      title: index ? '<script>unsafe()</script>' : 'Known history',
      creator: null,
      thumbnail_url: 'javascript:unsafe()',
      duration_seconds: null,
      upload_date: null,
      view_count: null,
      has_download_history: !index,
      has_file: false,
    })),
    statistics: {
      enumerated_count: 2,
      rejected_count: 0,
      duplicate_count: 0,
      metadata_unavailable_count: 0,
      filtered_count: 0,
      returned_count: 2,
      already_downloaded_count: 1,
      scan_limit: 100,
    },
  }
}
const result: BatchResult = {
  jobs: [{ id: 'job-real', status: 'queued' }],
  outcomes: [{ platform_video_id: ids[1], outcome: 'queued', job_id: 'job-real' }],
  requested_count: 1,
  created_count: 1,
  skipped_history_count: 0,
  skipped_duplicate_selection_count: 0,
}
const mountView = () =>
  mount(BatchView, {
    global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
async function previewView(wrapper: ReturnType<typeof mountView>): Promise<void> {
  await wrapper.get('#source-url').setValue(criteria.url)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}
beforeEach(() => {
  setActivePinia(createPinia())
  vi.mocked(api.resolveSource).mockReset().mockResolvedValue(sourcePreview())
  vi.mocked(api.submitBatch).mockReset().mockResolvedValue(result)
})
describe('Batch view', () => {
  it('uses backend capabilities, renders unknown metadata and escapes titles', async () => {
    const wrapper = mountView()
    await previewView(wrapper)
    expect(wrapper.get('#duration-min').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#date-from').attributes('disabled')).toBeDefined()
    expect(wrapper.get('#views-min').attributes('disabled')).toBeDefined()
    for (const order of ['newest', 'oldest', 'views'])
      expect(wrapper.get(`option[value="${order}"]`).attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Duration unknown')
    expect(wrapper.text()).toContain('Date unknown')
    expect(wrapper.text()).toContain('Views unknown')
    expect(wrapper.text()).toContain('<script>unsafe()</script>')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(api.submitBatch).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('selects eligible candidates, handles force and queues selected IDs with real options', async () => {
    const wrapper = mountView()
    await previewView(wrapper)
    const store = useBatchStore()
    store.selectAll(false)
    expect(store.selectedIds).toEqual([ids[1]])
    store.clear()
    expect(store.selectedIds).toEqual([])
    store.selectAll(false)
    expect(wrapper.findAll('.batch-card input')[0].attributes('disabled')).toBeDefined()
    await wrapper.get('#batch-force').setValue(true)
    store.selectAll(true)
    expect(store.selectedIds).toEqual(ids)
    await wrapper.get('#batch-force').setValue(false)
    expect(store.selectedIds).toEqual([ids[1]])
    await wrapper.get('#batch-height').setValue(720)
    await wrapper.get('#batch-container').setValue('mkv')
    await wrapper.get('#batch-audio').setValue(false)
    await wrapper.get('#batch-target').setValue('google_drive')
    expect(store.valid).toBe(true)
    await wrapper.get('#batch-submit').trigger('click')
    await flushPromises()
    expect(api.resolveSource).toHaveBeenCalledTimes(1)
    expect(api.submitBatch).toHaveBeenCalledWith({
      preview_id: sourcePreview().preview_id,
      selected_ids: [ids[1]],
      max_height: 720,
      preferred_container: 'mkv',
      audio_enabled: false,
      storage_target: 'google_drive',
      force: false,
    })
    expect(wrapper.text()).toContain('1 jobs queued')
    expect(wrapper.text()).toContain('View Queue')
    expect(store.valid).toBe(false)
    expect(wrapper.get('#batch-submit').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it.each(['#batch-n', '#duration-min', '#duration-max', '#source-url'])(
    'invalidates candidates and selection when %s changes',
    async (selector) => {
      const wrapper = mountView()
      await previewView(wrapper)
      useBatchStore().selectAll(false)
      await wrapper
        .get(selector)
        .setValue(selector === '#source-url' ? 'https://youtube.com/@other' : '10')
      expect(useBatchStore().preview).toBeNull()
      expect(useBatchStore().selectedIds).toEqual([])
      expect(wrapper.find('#batch-submit').exists()).toBe(false)
      wrapper.unmount()
    },
  )
  it.each(['0', '101', '1.5', ''])('rejects invalid N %s before API access', async (n) => {
    const wrapper = mountView()
    await wrapper.get('#source-url').setValue(criteria.url)
    await wrapper.get('#batch-n').setValue(n)
    await wrapper.get('form').trigger('submit')
    expect(api.resolveSource).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('N must be an integer')
    wrapper.unmount()
  })
  it('validates duration ranges and submits inclusive zero bounds', async () => {
    const wrapper = mountView()
    await previewView(wrapper)
    await wrapper.get('#duration-min').setValue('10')
    await wrapper.get('#duration-max').setValue('0')
    await wrapper.get('form').trigger('submit')
    expect(api.resolveSource).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('Minimum must not exceed maximum')
    await wrapper.get('#duration-min').setValue('0')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.resolveSource).toHaveBeenLastCalledWith(
      expect.objectContaining({ min_duration: 0, max_duration: 0 }),
      expect.any(AbortSignal),
    )
    wrapper.unmount()
  })
  it.each(['', 'not-a-url', 'file:///private'])(
    'rejects invalid source URL %s before API access',
    async (url) => {
      const wrapper = mountView()
      await wrapper.get('#source-url').setValue(url)
      await wrapper.get('form').trigger('submit')
      expect(api.resolveSource).not.toHaveBeenCalled()
      expect(wrapper.find('[role="alert"]').exists()).toBe(true)
      wrapper.unmount()
    },
  )
  it('shows unsupported source and offline errors, then recovers by explicit preview', async () => {
    vi.mocked(api.resolveSource).mockRejectedValueOnce(
      new ApiError('Listing unavailable', 'SOURCE_LIST_UNSUPPORTED'),
    )
    const wrapper = mountView()
    await previewView(wrapper)
    expect(wrapper.text()).toContain('Listing unavailable')
    expect(wrapper.find('#batch-submit').exists()).toBe(false)
    vi.mocked(api.resolveSource).mockRejectedValueOnce(
      new ApiError('Backend unavailable', 'NETWORK_ERROR'),
    )
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Backend unavailable')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(useBatchStore().valid).toBe(true)
    wrapper.unmount()
  })
})
describe('Batch lifecycle', () => {
  it('blocks repeated loading and submission while pending', async () => {
    const store = useBatchStore()
    let resolve!: (value: BatchResult) => void
    await store.load(criteria)
    store.selectAll(false)
    vi.mocked(api.submitBatch).mockImplementation(
      () =>
        new Promise((yes) => {
          resolve = yes
        }),
    )
    const first = store.submit(options)
    await store.submit(options)
    await store.load(criteria)
    expect(api.submitBatch).toHaveBeenCalledTimes(1)
    expect(api.resolveSource).toHaveBeenCalledTimes(1)
    resolve(result)
    await first
    expect(store.result).toEqual(result)
  })
  it('drops stale responses after criteria changes and aborts on unmount', async () => {
    let resolve!: (value: SourcePreview) => void
    vi.mocked(api.resolveSource).mockImplementation(
      () =>
        new Promise((yes) => {
          resolve = yes
        }),
    )
    const wrapper = mountView()
    await wrapper.get('#source-url').setValue(criteria.url)
    await wrapper.get('form').trigger('submit')
    const signal = vi.mocked(api.resolveSource).mock.calls[0][1]!
    await wrapper.get('#batch-n').setValue('5')
    expect(signal.aborted).toBe(true)
    resolve(sourcePreview())
    await flushPromises()
    expect(useBatchStore().preview).toBeNull()
    await wrapper.get('form').trigger('submit')
    const second = vi.mocked(api.resolveSource).mock.calls[1][1]!
    wrapper.unmount()
    expect(second.aborted).toBe(true)
    resolve(sourcePreview())
    await flushPromises()
    expect(useBatchStore().preview).toBeNull()
  })
  it('rejects arbitrary selection and handles expired previews without fake history changes', async () => {
    const store = useBatchStore()
    await store.load(criteria)
    store.select('outside0001', true, true)
    store.select(ids[0], true, false)
    expect(store.selectedIds).toEqual([])
    store.selectAll(false)
    vi.mocked(api.submitBatch).mockRejectedValue(
      new ApiError('Preview expired', 'SOURCE_PREVIEW_EXPIRED'),
    )
    await store.submit(options)
    expect(store.valid).toBe(false)
    expect(store.selectedIds).toEqual([])
    expect(store.result).toBeNull()
    expect(store.preview?.candidates[1].has_download_history).toBe(false)
  })
  it('retains valid selection after a failed submission and clears server summary on navigation', async () => {
    const store = useBatchStore()
    await store.load(criteria)
    store.selectAll(false)
    vi.mocked(api.submitBatch).mockRejectedValueOnce(
      new ApiError('Destination unavailable', 'STORAGE_NOT_CONNECTED'),
    )
    await store.submit(options)
    expect(store.valid).toBe(true)
    expect(store.selectedIds).toEqual([ids[1]])
    let resolve!: (value: BatchResult) => void
    vi.mocked(api.submitBatch).mockImplementation(
      () =>
        new Promise((yes) => {
          resolve = yes
        }),
    )
    const pending = store.submit(options)
    store.invalidate(true)
    resolve(result)
    await pending
    expect(store.result).toBeNull()
    expect(store.preview).toBeNull()
  })
  it('updates backend connection health on Batch failure and recovery', async () => {
    const health = useHealthStore()
    health.status = 'reachable'
    const store = useBatchStore()
    vi.mocked(api.resolveSource).mockRejectedValueOnce(new ApiError('Offline', 'NETWORK_ERROR'))
    await store.load(criteria)
    expect(health.status).toBe('unreachable')
    await store.load(criteria)
    expect(health.status).toBe('reachable')
  })
})
