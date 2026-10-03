import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../src/api/storage'
import * as downloads from '../src/api/downloads'
import { ApiError } from '../src/api/client'
import { useStorageStore } from '../src/stores/storage'
import StorageView from '../src/views/StorageView.vue'
import DownloadView from '../src/views/DownloadView.vue'
import type { StorageStatus } from '../src/types/storage'

vi.mock('../src/api/storage', () => ({
  fetchStorage: vi.fn(),
  connectDrive: vi.fn(),
  disconnectDrive: vi.fn(),
  setDriveRoot: vi.fn(),
}))
vi.mock('../src/api/downloads', () => ({ submitDownloads: vi.fn(), resolvePreview: vi.fn() }))
const status = (connected = false, configured = true): StorageStatus => ({
  default_target: 'local',
  providers: [
    {
      provider: 'local',
      configured: true,
      connected: true,
      available: true,
      display_name: null,
      account_id: null,
      root_folder_id: null,
      error_code: null,
    },
    {
      provider: 'google_drive',
      configured,
      connected,
      available: connected,
      display_name: connected ? 'Test account' : null,
      account_id: connected ? 'test-id' : null,
      root_folder_id: connected ? 'root-folder' : null,
      error_code: null,
    },
  ],
})
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  vi.mocked(api.fetchStorage).mockResolvedValue(status())
})
async function mountStorage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/storage', component: StorageView }],
  })
  await router.push('/storage')
  const wrapper = mount(StorageView, { global: { plugins: [createPinia(), router] } })
  await flushPromises()
  return wrapper
}
it('shows unconfigured Drive without an enabled connect action', async () => {
  vi.mocked(api.fetchStorage).mockResolvedValue(status(false, false))
  const wrapper = await mountStorage()
  expect(wrapper.text()).toContain('Not configured')
  expect(wrapper.findAll('button').some((button) => button.text() === 'Connect Google Drive')).toBe(
    false,
  )
  wrapper.unmount()
})
it('connects through a backend authorization URL without fake connected state', async () => {
  vi.mocked(api.connectDrive).mockResolvedValue({
    authorization_url: 'https://accounts.google.com/o/oauth2/auth?state=test',
  })
  const wrapper = await mountStorage()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Connect Google Drive')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.get('a').attributes('href')).toContain('accounts.google.com')
  expect(wrapper.text()).toContain('Not connected')
  wrapper.unmount()
})
it('selects a root through the backend and disconnects only after confirmation', async () => {
  vi.mocked(api.fetchStorage).mockResolvedValue(status(true))
  vi.mocked(api.setDriveRoot).mockResolvedValue({ id: 'new-root', name: 'Research' })
  vi.mocked(api.disconnectDrive).mockResolvedValue(status())
  const wrapper = await mountStorage()
  const disconnect = wrapper
    .findAll('button')
    .find((button) => button.text() === 'Disconnect Google Drive')!
  expect(disconnect.attributes('disabled')).toBeDefined()
  await wrapper.get('#drive-root').setValue('new-root')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api.setDriveRoot).toHaveBeenCalledWith('new-root')
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await disconnect.trigger('click')
  await flushPromises()
  expect(api.disconnectDrive).toHaveBeenCalledOnce()
  expect(wrapper.text()).toContain('Not connected')
  wrapper.unmount()
})
it('preserves cached status on offline failure, disables Drive and recovers', async () => {
  const store = useStorageStore()
  vi.mocked(api.fetchStorage).mockResolvedValue(status(true))
  await store.load()
  vi.mocked(api.fetchStorage).mockRejectedValueOnce(new ApiError('Offline', 'NETWORK_ERROR'))
  await store.load()
  expect(store.drive?.connected).toBe(true)
  expect(store.driveReady).toBe(false)
  expect(store.error).toBe('Offline')
  await store.load()
  expect(store.driveReady).toBe(true)
  expect(store.error).toBeNull()
})
it('serializes repeated storage actions and displays server failures', async () => {
  const store = useStorageStore()
  let reject!: (value: Error) => void
  vi.mocked(api.connectDrive).mockImplementation(
    () =>
      new Promise((_, no) => {
        reject = no
      }),
  )
  const first = store.action('connect')
  await store.action('connect')
  expect(api.connectDrive).toHaveBeenCalledOnce()
  reject(new ApiError('OAuth failed safely', 'OAUTH_FAILED'))
  await first
  expect(store.error).toBe('OAuth failed safely')
  expect(store.busy).toBe(false)
})
it.each([true, false])(
  'respects Drive default and availability %s without silent fallback',
  async (connected) => {
    vi.mocked(api.fetchStorage).mockResolvedValue({
      ...status(connected),
      default_target: 'google_drive',
    })
    vi.mocked(downloads.submitDownloads).mockResolvedValue({
      jobs: [{ id: 'job', status: 'queued' }],
    })
    const wrapper = mount(DownloadView, {
      global: { plugins: [createPinia()], stubs: { RouterLink: true } },
    })
    await flushPromises()
    expect((wrapper.get('#storage-target').element as HTMLSelectElement).value).toBe('google_drive')
    await wrapper.get('textarea').setValue('https://youtube.com/watch?v=test')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    if (connected)
      expect(downloads.submitDownloads).toHaveBeenCalledWith(
        expect.objectContaining({ storage_target: 'google_drive' }),
      )
    else expect(downloads.submitDownloads).not.toHaveBeenCalled()
    wrapper.unmount()
  },
)
