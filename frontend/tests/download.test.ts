import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DownloadView from '../src/views/DownloadView.vue'
import * as api from '../src/api/downloads'
import { ApiError } from '../src/api/client'
import { parseUrls, validateUrls } from '../src/utils/download'

vi.mock('../src/api/downloads', () => ({ submitDownloads: vi.fn(), resolvePreview: vi.fn() }))
const mountForm = () =>
  mount(DownloadView, {
    global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
describe('Quick Download', () => {
  it('submits explicit force redownload without changing the download API', async () => {
    vi.mocked(api.submitDownloads).mockResolvedValue({ jobs: [{ id: 'forced', status: 'queued' }] })
    const wrapper = mountForm()
    await wrapper.get('textarea').setValue('https://youtube.com/watch?v=a')
    await wrapper.findAll('input[type="checkbox"]')[1].setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.submitDownloads).toHaveBeenCalledWith(expect.objectContaining({ force: true }))
    wrapper.unmount()
  })
  beforeEach(() => {
    vi.mocked(api.submitDownloads).mockReset()
    vi.mocked(api.resolvePreview).mockReset()
  })
  it('normalizes pasted lines and rejects too many URLs', () => {
    expect(
      parseUrls(' https://a.test/video \r\n\nhttps://b.test/video\nhttps://a.test/video '),
    ).toEqual(['https://a.test/video', 'https://b.test/video'])
    expect(
      validateUrls(Array.from({ length: 101 }, (_, i) => `https://example.com/${i}`)),
    ).toContain('100')
  })
  it.each(['', 'not-a-url', 'file:///private'])(
    'rejects invalid input without API submission',
    async (text) => {
      const wrapper = mountForm()
      await wrapper.get('textarea').setValue(text)
      await wrapper.get('form').trigger('submit')
      expect(wrapper.find('[role="alert"]').exists()).toBe(true)
      expect(api.submitDownloads).not.toHaveBeenCalled()
      wrapper.unmount()
    },
  )
  it('submits multiple URLs with real options and links to the created queue', async () => {
    vi.mocked(api.submitDownloads).mockResolvedValue({
      jobs: [
        { id: 'one', status: 'queued' },
        { id: 'two', status: 'queued' },
      ],
    })
    const wrapper = mountForm()
    await wrapper
      .get('textarea')
      .setValue(' https://youtube.com/watch?v=a \n\nhttps://tiktok.com/@user/video/123 ')
    await wrapper.get('#max-height').setValue(720)
    await wrapper.get('#container').setValue('mkv')
    await wrapper.get('input[type="checkbox"]').setValue(false)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.submitDownloads).toHaveBeenCalledWith({
      urls: ['https://youtube.com/watch?v=a', 'https://tiktok.com/@user/video/123'],
      max_height: 720,
      preferred_container: 'mkv',
      audio_enabled: false,
    })
    expect(wrapper.text()).toContain('2 jobs created')
    expect(api.resolvePreview).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('disables duplicate submissions and presents the server validation message', async () => {
    let reject!: (error: Error) => void
    vi.mocked(api.submitDownloads).mockImplementation(
      () =>
        new Promise((_, no) => {
          reject = no
        }),
    )
    const wrapper = mountForm()
    await wrapper.get('textarea').setValue('https://youtube.com/watch?v=a')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(api.submitDownloads).toHaveBeenCalledTimes(1)
    reject(new ApiError('Request validation failed', 'VALIDATION_ERROR', 422))
    await flushPromises()
    expect(wrapper.text()).toContain('Request validation failed')
    wrapper.unmount()
  })
  it('escapes external metadata and does not embed unsafe image URLs', async () => {
    vi.mocked(api.resolvePreview).mockResolvedValue({
      platform: 'youtube',
      platform_video_id: 'video',
      canonical_url: 'https://youtube.com/watch?v=a',
      title: '<script>unsafe()</script>',
      creator: '<img onerror=unsafe()>',
      duration_seconds: 3,
      width: 1920,
      height: 1080,
      thumbnail_url: 'javascript:unsafe()',
    })
    const wrapper = mountForm()
    await wrapper.get('textarea').setValue('https://youtube.com/watch?v=a')
    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('<script>unsafe()</script>')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(api.submitDownloads).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('discards stale preview results after input changes', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof api.resolvePreview>>) => void
    vi.mocked(api.resolvePreview).mockImplementation(
      () =>
        new Promise((yes) => {
          resolve = yes
        }),
    )
    const wrapper = mountForm()
    await wrapper.get('textarea').setValue('https://youtube.com/watch?v=a')
    await wrapper.findAll('button')[1].trigger('click')
    await wrapper.get('textarea').setValue('https://youtube.com/watch?v=b')
    resolve({
      platform: 'youtube',
      platform_video_id: 'a',
      canonical_url: 'https://youtube.com/watch?v=a',
      title: 'Old video',
      creator: null,
      duration_seconds: null,
      width: null,
      height: null,
      thumbnail_url: null,
    })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Old video')
    wrapper.unmount()
  })
})
