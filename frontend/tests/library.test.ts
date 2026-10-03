import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../src/api/library'
import { ApiError } from '../src/api/client'
import { useLibraryStore } from '../src/stores/library'
import { useHistoryStore } from '../src/stores/history'
import { useHealthStore } from '../src/stores/health'
import LibraryView from '../src/views/LibraryView.vue'
import HistoryView from '../src/views/HistoryView.vue'
import type { LibraryVideo, VideoDetail, HistoryItem, Page } from '../src/types/library'

vi.mock('../src/api/library', () => ({
  fetchLibrary: vi.fn(),
  fetchDetail: vi.fn(),
  fetchHistory: vi.fn(),
  fetchNamed: vi.fn(),
  createNamed: vi.fn(),
  attachNamed: vi.fn(),
  destroyVideo: vi.fn(),
  forceRedownload: vi.fn(),
  refreshFiles: vi.fn(),
}))
const video: LibraryVideo = {
  id: 'v',
  platform: 'youtube',
  platform_video_id: 'source',
  title: 'Actual research clip',
  creator: 'Creator',
  thumbnail_url: null,
  duration_seconds: 0.3,
  upload_date: null,
  view_count: 0,
  width: 64,
  height: 48,
  has_file: true,
  has_download_history: true,
  tags: [],
  collections: [],
}
const event: HistoryItem = {
  id: 'd',
  video_id: 'v',
  title: video.title,
  platform: 'youtube',
  status: 'completed',
  forced: true,
  attempt_number: 1,
  job_id: 'j',
  requested_quality: '{"max_height":1080,"preferred_container":"mp4","audio_enabled":true}',
  created_at: '2026-10-03T00:00:00Z',
  started_at: null,
  completed_at: null,
  failure_code: null,
  failure_message: null,
}
const detail: VideoDetail = {
  ...video,
  description: 'Metadata survives',
  files: [
    {
      id: 'm',
      storage_provider: 'local',
      file_name: 'clip.mp4',
      size_bytes: 120,
      sha256: 'a'.repeat(64),
      container: 'mp4',
      width: 64,
      height: 48,
      state: 'available',
    },
  ],
  history: [event],
}
const page = <T>(items: T[], total = items.length): Page<T> => ({
  items,
  total,
  page: 1,
  page_size: 25,
})
const mountPage = (component: typeof LibraryView | typeof HistoryView) =>
  mount(component, { global: { plugins: [createPinia()], stubs: { RouterLink: true } } })
const click = async (wrapper: ReturnType<typeof mountPage>, text: string) => {
  const button = wrapper.findAll('button').find((item) => item.text() === text)
  expect(button, text).toBeDefined()
  await button!.trigger('click')
  await flushPromises()
}
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  vi.mocked(api.fetchLibrary).mockResolvedValue(page([video]))
  vi.mocked(api.fetchHistory).mockResolvedValue(page([event]))
  vi.mocked(api.fetchDetail).mockResolvedValue(detail)
  vi.mocked(api.fetchNamed).mockResolvedValue([])
  vi.mocked(api.forceRedownload).mockResolvedValue({ jobs: [{ id: 'new-job', status: 'queued' }] })
  vi.mocked(api.destroyVideo).mockResolvedValue({ ...detail, has_file: false })
  vi.mocked(api.createNamed).mockResolvedValue({ id: 'organization', name: 'Research' })
  vi.mocked(api.attachNamed).mockResolvedValue(detail)
})
describe('Phase 07 library/history UI', () => {
  it('renders real data and distinct file/history combinations with escaped metadata', async () => {
    vi.mocked(api.fetchLibrary).mockResolvedValue(
      page([
        { ...video, title: '<img onerror=alert(1)>', has_file: false },
        { ...video, id: 'v2', has_download_history: false },
      ]),
    )
    const wrapper = mountPage(LibraryView)
    await flushPromises()
    expect(wrapper.text()).toContain('<img onerror=alert(1)>')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.findAll('article')[0].text()).toContain('Stored file: No file')
    expect(wrapper.findAll('article')[1].text()).toContain('No successful history')
    wrapper.unmount()
  })
  it('shows a genuine empty Library and History', async () => {
    vi.mocked(api.fetchLibrary).mockResolvedValue(page([]))
    vi.mocked(api.fetchHistory).mockResolvedValue(page([]))
    const library = mountPage(LibraryView)
    const history = mountPage(HistoryView)
    await flushPromises()
    expect(library.text()).toContain('No videos match this view')
    expect(history.text()).toContain('No download history yet')
    library.unmount()
    history.unmount()
  })
  it('renders actual history events with forced state and safe failures', async () => {
    vi.mocked(api.fetchHistory).mockResolvedValue(
      page([
        event,
        {
          ...event,
          id: 'failure',
          status: 'failed',
          failure_code: 'DOWNLOAD_FAILED',
          failure_message: 'Media download failed',
        },
      ]),
    )
    const wrapper = mountPage(HistoryView)
    await flushPromises()
    expect(wrapper.text()).toContain('Actual research clip')
    expect(wrapper.text()).toContain('Forced redownload')
    expect(wrapper.text()).toContain('DOWNLOAD_FAILED')
    expect(wrapper.text()).not.toContain('Invalid Date')
    wrapper.unmount()
  })
  it('searches explicitly, uses supported filters and paginates', async () => {
    vi.mocked(api.fetchLibrary).mockResolvedValue(page([video], 26))
    const wrapper = mountPage(LibraryView)
    await flushPromises()
    await wrapper.get('#library-search').setValue('Creator')
    expect(api.fetchLibrary).toHaveBeenCalledTimes(1)
    await wrapper.get('#library-platform').setValue('youtube')
    await wrapper.get('#file-filter').setValue('no')
    await wrapper.get('#history-filter').setValue('yes')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.fetchLibrary).toHaveBeenLastCalledWith(
      expect.objectContaining({
        search: 'Creator',
        platform: 'youtube',
        has_file: false,
        has_download_history: true,
      }),
      1,
      expect.any(AbortSignal),
    )
    await click(wrapper, 'Next')
    expect(api.fetchLibrary).toHaveBeenLastCalledWith(expect.anything(), 2, expect.any(AbortSignal))
    wrapper.unmount()
  })
  it('filters and paginates History', async () => {
    vi.mocked(api.fetchHistory).mockResolvedValue(page([event], 26))
    const wrapper = mountPage(HistoryView)
    await flushPromises()
    await wrapper.get('#history-platform').setValue('youtube')
    await wrapper.get('#history-status').setValue('completed')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.fetchHistory).toHaveBeenLastCalledWith(
      1,
      { platform: 'youtube', status: 'completed' },
      expect.any(AbortSignal),
    )
    await click(wrapper, 'Next')
    expect(api.fetchHistory).toHaveBeenLastCalledWith(2, expect.anything(), expect.any(AbortSignal))
    wrapper.unmount()
  })
  it.each([
    ['Delete file', 'file', 'history will remain'],
    ['Remove history', 'history', 'media files will remain'],
    ['Delete everything', 'all', 'metadata, tags and collections remain'],
  ] as const)(
    'requires explicit %s confirmation with truthful semantics',
    async (label, operation, expectedCopy) => {
      const wrapper = mountPage(LibraryView)
      await flushPromises()
      await click(wrapper, 'View details')
      await click(wrapper, label)
      expect(api.destroyVideo).not.toHaveBeenCalled()
      expect(wrapper.get('[role="alertdialog"]').text().toLowerCase()).toContain(expectedCopy)
      if (operation === 'all') {
        expect(
          wrapper
            .findAll('button')
            .find((item) => item.text() === 'Confirm action')
            ?.attributes('disabled'),
        ).toBeDefined()
        await wrapper.get('#confirm-delete').setValue('DELETE')
      }
      await click(wrapper, 'Confirm action')
      expect(api.destroyVideo).toHaveBeenCalledWith('v', operation)
      expect(wrapper.find('[role="alertdialog"]').exists()).toBe(false)
      wrapper.unmount()
    },
  )
  it('cancels confirmation without mutation, and force queues a server job', async () => {
    const wrapper = mountPage(LibraryView)
    await flushPromises()
    await click(wrapper, 'View details')
    await click(wrapper, 'Delete file')
    await click(wrapper, 'Keep current state')
    expect(api.destroyVideo).not.toHaveBeenCalled()
    await click(wrapper, 'Force redownload')
    expect(api.forceRedownload).toHaveBeenCalledWith('v')
    expect(wrapper.text()).toContain('redownload job queued')
    wrapper.unmount()
  })
  it('creates/attaches and removes personal tags and collections', async () => {
    vi.mocked(api.fetchDetail).mockResolvedValue({
      ...detail,
      tags: [{ id: 'tag', name: 'Saved' }],
      collections: [{ id: 'collection', name: 'Study' }],
    })
    const wrapper = mountPage(LibraryView)
    await flushPromises()
    await click(wrapper, 'View details')
    await click(wrapper, 'Remove tag')
    expect(api.attachNamed).toHaveBeenCalledWith('tags', 'v', 'tag', true)
    useLibraryStore().selected = { ...detail, collections: [{ id: 'collection', name: 'Study' }] }
    await flushPromises()
    await click(wrapper, 'Remove collection')
    expect(api.attachNamed).toHaveBeenCalledWith('collections', 'v', 'collection', true)
    await wrapper.get('#tag-name').setValue('Research')
    await click(wrapper, 'Add tag')
    expect(api.createNamed).toHaveBeenCalledWith('tags', 'Research')
    expect(api.attachNamed).toHaveBeenCalledWith('tags', 'v', 'organization', false)
    await wrapper.get('#collection-name').setValue('Study')
    await click(wrapper, 'Add collection')
    expect(api.createNamed).toHaveBeenCalledWith('collections', 'Study')
    wrapper.unmount()
  })
  it('keeps loaded Library data on failure, recovers and reloads from backend after remount', async () => {
    const wrapper = mountPage(LibraryView)
    await flushPromises()
    vi.mocked(api.fetchLibrary).mockRejectedValueOnce(
      new ApiError('Cannot connect', 'NETWORK_ERROR'),
    )
    await click(wrapper, 'Refresh')
    expect(wrapper.text()).toContain('Cannot connect')
    expect(wrapper.text()).toContain(video.title)
    await click(wrapper, 'Refresh')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
    const reloaded = mountPage(LibraryView)
    await flushPromises()
    expect(reloaded.text()).toContain(video.title)
    reloaded.unmount()
  })
  it('renders History network failure and keeps cached events', async () => {
    const wrapper = mountPage(HistoryView)
    await flushPromises()
    vi.mocked(api.fetchHistory).mockRejectedValueOnce(
      new ApiError('Cannot connect', 'NETWORK_ERROR'),
    )
    await click(wrapper, 'Refresh')
    expect(wrapper.text()).toContain('Cannot connect')
    expect(wrapper.text()).toContain(event.title)
    wrapper.unmount()
  })
  it('keeps details on destructive failure without claiming success', async () => {
    vi.mocked(api.destroyVideo).mockRejectedValueOnce(
      new ApiError('File operation failed', 'FILE_DELETE_FAILED', 400),
    )
    const wrapper = mountPage(LibraryView)
    await flushPromises()
    await click(wrapper, 'View details')
    await click(wrapper, 'Delete file')
    await click(wrapper, 'Confirm action')
    expect(wrapper.text()).toContain('File operation failed')
    expect(useLibraryStore().selected?.has_file).toBe(true)
    expect(wrapper.find('[role="alertdialog"]').exists()).toBe(true)
    wrapper.unmount()
  })
  it.each(['library', 'history'] as const)(
    'returns to a valid %s page when the final page disappears',
    async (kind) => {
      const read = kind === 'library' ? api.fetchLibrary : api.fetchHistory
      if (kind === 'library')
        vi.mocked(api.fetchLibrary)
          .mockResolvedValueOnce({ ...page<LibraryVideo>([], 25), page: 2 })
          .mockResolvedValueOnce(page([video], 25))
      else
        vi.mocked(api.fetchHistory)
          .mockResolvedValueOnce({ ...page<HistoryItem>([], 25), page: 2 })
          .mockResolvedValueOnce(page([event], 25))
      const store = kind === 'library' ? useLibraryStore() : useHistoryStore()
      await store.load(2)
      expect(read).toHaveBeenCalledTimes(2)
      expect(store.page).toBe(1)
      expect(store.items).toHaveLength(1)
      expect(store.loading).toBe(false)
    },
  )
  it.each(['library', 'history'] as const)(
    'updates backend connection health when %s fails and recovers',
    async (kind) => {
      const health = useHealthStore()
      health.status = 'reachable'
      const failure = new ApiError('Backend offline', 'NETWORK_ERROR')
      if (kind === 'library') vi.mocked(api.fetchLibrary).mockRejectedValueOnce(failure)
      else vi.mocked(api.fetchHistory).mockRejectedValueOnce(failure)
      const store = kind === 'library' ? useLibraryStore() : useHistoryStore()
      await store.load()
      expect(health.status).toBe('unreachable')
      await store.load()
      expect(health.status).toBe('reachable')
    },
  )
  it('reconciles truthful file markers after partial deletion while retaining the action error', async () => {
    const store = useLibraryStore()
    store.selected = {
      ...detail,
      files: [detail.files[0], { ...detail.files[0], id: 'second-file' }],
    }
    vi.mocked(api.destroyVideo).mockRejectedValueOnce(
      new ApiError('One file could not be deleted', 'STORAGE_DELETE_FAILED', 400),
    )
    vi.mocked(api.fetchDetail).mockResolvedValueOnce({
      ...store.selected,
      files: [
        { ...detail.files[0], state: 'deleted' },
        { ...detail.files[0], id: 'second-file' },
      ],
    })
    await store.action('file')
    expect(api.fetchDetail).toHaveBeenCalledWith('v', expect.any(AbortSignal))
    expect(store.selected?.files.map((file) => file.state)).toEqual(['deleted', 'available'])
    expect(store.actionError).toBe('One file could not be deleted')
    expect(store.busy).toBe(false)
  })
  it('does not restart Library reads after a mutation finishes on an unmounted page', async () => {
    const store = useLibraryStore()
    store.selected = detail
    let finish!: (value: VideoDetail) => void
    vi.mocked(api.destroyVideo).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const mutation = store.action('file')
    store.stop()
    finish({ ...detail, has_file: false })
    await mutation
    expect(api.fetchLibrary).not.toHaveBeenCalled()
    expect(store.busy).toBe(false)
    expect(store.loading).toBe(false)
  })
})

it('labels Drive as last-known and performs only an explicit targeted refresh', async () => {
  const driveDetail: VideoDetail = {
    ...detail,
    files: [{ ...detail.files[0], storage_provider: 'google_drive', state: 'stored' }],
  }
  vi.mocked(api.fetchDetail).mockResolvedValue(driveDetail)
  vi.mocked(api.refreshFiles).mockResolvedValue({
    ...driveDetail,
    files: [{ ...driveDetail.files[0], state: 'missing' }],
  })
  const wrapper = mountPage(LibraryView)
  await flushPromises()
  await click(wrapper, 'View details')
  expect(wrapper.text()).toContain('Google Drive')
  expect(wrapper.text()).toContain('Stored (last-known)')
  expect(api.refreshFiles).not.toHaveBeenCalled()
  await click(wrapper, 'Refresh file availability')
  expect(api.refreshFiles).toHaveBeenCalledWith('v')
  expect(wrapper.text()).toContain('missing')
  wrapper.unmount()
})
