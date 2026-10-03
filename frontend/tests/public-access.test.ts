import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { routes } from '../src/router'
import { useDownloadsStore } from '../src/stores/downloads'
import type { VideoPreview } from '../src/types/api'
import type { JobStatus } from '../src/types/jobs'
import { job, jobPage } from './fixtures'

const failures = [
  {
    code: 'PLATFORM_ACCESS_BLOCKED',
    message:
      'YouTube blocked anonymous access from this environment. The video may still be public.',
  },
  {
    code: 'EXTRACTOR_RUNTIME_UNAVAILABLE',
    message: 'YouTube extraction requires the configured JavaScript runtime support.',
  },
] as const
const publicUrl = 'https://www.youtube.com/watch?v=public00001'
const preview: VideoPreview = {
  platform: 'youtube',
  platform_video_id: 'public00001',
  canonical_url: publicUrl,
  title: 'Public fixture video',
  creator: null,
  duration_seconds: 5,
  width: 64,
  height: 48,
  thumbnail_url: null,
  video_id: null,
  has_file: false,
  has_download_history: false,
}
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status })
const errorResponse = (failure: (typeof failures)[number]) =>
  json({ error: { ...failure, details: { diagnostic: 'fixture-private-diagnostic' } } }, 400)

async function mountWorkflow(
  failure: (typeof failures)[number],
  resolvePreview: (signal: AbortSignal) => Promise<Response>,
) {
  let serverJob = job({ status: 'failed', attempt_count: 1, error: failure })
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    const url = new URL(input, 'http://localhost')
    if (url.pathname === '/api/v1/videos/resolve')
      return resolvePreview(init!.signal as AbortSignal)
    if (url.pathname === '/api/v1/storage')
      return json({
        default_target: 'local',
        providers: ['local', 'google_drive'].map((provider) => ({
          provider,
          configured: provider === 'local',
          connected: provider === 'local',
          available: provider === 'local',
          display_name: null,
          account_id: null,
          root_folder_id: null,
          error_code: null,
        })),
      })
    if (url.pathname === '/api/v1/queue') return json({ paused: false })
    if (url.pathname === `/api/v1/jobs/${serverJob.id}/retry`) {
      serverJob = job({ attempt_count: 1 })
      return json(serverJob)
    }
    if (url.pathname === '/api/v1/jobs')
      return json(
        jobPage([serverJob], {
          page: Number(url.searchParams.get('page') || 1),
          page_size: Number(url.searchParams.get('page_size') || 25),
          status: (url.searchParams.get('status') || undefined) as JobStatus | undefined,
        }),
      )
    throw new Error(`Unexpected fixture endpoint: ${url.pathname}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/download')
  const pinia = createPinia()
  const wrapper = mount(RouterView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  await wrapper.get('textarea').setValue(publicUrl)
  return { wrapper, router, store: useDownloadsStore(pinia), fetchMock }
}

type Workflow = Awaited<ReturnType<typeof mountWorkflow>>
const button = (workflow: Workflow, text: string) => {
  const found = workflow.wrapper.findAll('button').find((item) => item.text() === text)
  expect(found, text).toBeDefined()
  return found!
}

describe('public YouTube failures through the frontend HTTP boundary', () => {
  it.each(failures)(
    'shows $code truthfully, releases busy state and permits retry/navigation',
    async (failure) => {
      let attempts = 0
      const workflow = await mountWorkflow(failure, async () =>
        ++attempts === 1 ? errorResponse(failure) : json(preview),
      )
      try {
        await button(workflow, 'Preview video').trigger('click')
        await flushPromises()
        expect(workflow.wrapper.get('[role="alert"]').text()).toContain(failure.code)
        expect(workflow.wrapper.get('[role="alert"]').text()).toContain(failure.message)
        expect(workflow.wrapper.text()).not.toContain('AUTHENTICATION_REQUIRED')
        expect(workflow.wrapper.text()).not.toContain('fixture-private-diagnostic')
        expect(workflow.store.previewLoading).toBe(false)
        expect(button(workflow, 'Preview video').attributes('disabled')).toBeUndefined()
        await button(workflow, 'Preview video').trigger('click')
        await flushPromises()
        expect(workflow.wrapper.text()).toContain(preview.title)
        expect(workflow.wrapper.find('[role="alert"]').exists()).toBe(false)
        await workflow.router.push('/queue')
        await flushPromises()
        expect(workflow.wrapper.find('article').text()).toContain('Failed')
        expect(workflow.wrapper.find('article').text()).toContain(failure.code)
        expect(workflow.wrapper.find('article').text()).toContain(failure.message)
        expect(workflow.wrapper.find('article').text()).not.toContain('Completed')
        await button(workflow, 'Retry').trigger('click')
        await flushPromises()
        expect(workflow.wrapper.find('article').text()).toContain('Queued')
        expect(workflow.wrapper.find('article').text()).not.toContain(failure.code)
        expect(
          workflow.fetchMock.mock.calls.filter(([path]) => path.endsWith('/retry')),
        ).toHaveLength(1)
        await workflow.router.push('/download')
        await flushPromises()
        expect(workflow.wrapper.text()).toContain('Quick Download')
        expect(workflow.store.previewLoading).toBe(false)
      } finally {
        workflow.wrapper.unmount()
      }
    },
  )

  it.each(failures)(
    'discards late $code after navigation and uses a fresh preview request',
    async (failure) => {
      let finish!: (value: Response) => void
      const signals: AbortSignal[] = []
      const workflow = await mountWorkflow(failure, async (signal) => {
        signals.push(signal)
        expect(signal.aborted).toBe(false)
        if (signals.length === 1)
          return new Promise((resolve) => {
            finish = resolve
          })
        return errorResponse(failure)
      })
      try {
        await button(workflow, 'Preview video').trigger('click')
        expect(workflow.store.previewLoading).toBe(true)
        await workflow.router.push('/queue')
        await flushPromises()
        expect(signals[0].aborted).toBe(true)
        finish(errorResponse(failure))
        await flushPromises()
        expect(workflow.store.previewError).toBeNull()
        expect(workflow.store.previewLoading).toBe(false)
        await workflow.router.push('/download')
        await flushPromises()
        await workflow.wrapper.get('textarea').setValue(publicUrl)
        await button(workflow, 'Preview video').trigger('click')
        await flushPromises()
        expect(signals).toHaveLength(2)
        expect(workflow.wrapper.get('[role="alert"]').text()).toContain(failure.code)
        expect(workflow.store.previewLoading).toBe(false)
      } finally {
        workflow.wrapper.unmount()
      }
    },
  )
})
