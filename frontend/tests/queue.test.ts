import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as jobsApi from '../src/api/jobs'
import * as queueApi from '../src/api/queue'
import { ApiError } from '../src/api/client'
import { ACTIVE_POLL_MS, IDLE_POLL_MS, useQueueStore } from '../src/stores/queue'
import QueueView from '../src/views/QueueView.vue'
import DashboardView from '../src/views/DashboardView.vue'
import type { Job, JobPage, JobQuery } from '../src/types/jobs'
import { routes } from '../src/router'
import { job, jobPage } from './fixtures'

vi.mock('../src/api/jobs', () => ({
  fetchJobs: vi.fn(),
  fetchJob: vi.fn(),
  cancelJob: vi.fn(),
  retryJob: vi.fn(),
}))
vi.mock('../src/api/queue', () => ({
  fetchQueueState: vi.fn(),
  pauseQueue: vi.fn(),
  resumeQueue: vi.fn(),
}))
let serverJobs: Job[] = []
let serverPaused = false
beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  serverJobs = [job()]
  serverPaused = false
  vi.mocked(jobsApi.fetchJobs).mockImplementation(async (query: JobQuery = {}) =>
    jobPage(serverJobs, query),
  )
  vi.mocked(queueApi.fetchQueueState).mockImplementation(async () => ({ paused: serverPaused }))
  vi.mocked(queueApi.pauseQueue).mockImplementation(async () => {
    serverPaused = true
    return { paused: true }
  })
  vi.mocked(queueApi.resumeQueue).mockImplementation(async () => {
    serverPaused = false
    return { paused: false }
  })
})
afterEach(() => {
  useQueueStore().stopPolling()
  vi.useRealTimers()
})

describe('queue state and actions', () => {
  it('loads paginated jobs, real global counts and authoritative pause state', async () => {
    serverJobs = Array.from({ length: 30 }, (_, i) =>
      job({ id: String(i), status: i < 26 ? 'completed' : 'queued' }),
    )
    serverPaused = true
    const queue = useQueueStore()
    await queue.refresh()
    expect(queue.jobs).toHaveLength(25)
    expect(queue.total).toBe(30)
    expect(queue.counts).toEqual({ queued: 4, running: 0, completed: 26, failed: 0 })
    expect(queue.paused).toBe(true)
    expect(queue.hasWork).toBe(true)
    await queue.setPage(2)
    expect(queue.jobs).toHaveLength(5)
    await queue.setFilter('queued')
    expect(queue.page).toBe(1)
    expect(queue.total).toBe(4)
  })
  it('preserves loaded jobs on refresh failure and recovers later', async () => {
    const queue = useQueueStore()
    await queue.refresh()
    vi.mocked(jobsApi.fetchJobs).mockRejectedValueOnce(
      new ApiError('Cannot connect', 'NETWORK_ERROR'),
    )
    await queue.refresh()
    expect(queue.jobs).toEqual(serverJobs)
    expect(queue.error).toBe('Cannot connect')
    await queue.refresh()
    expect(queue.error).toBeNull()
  })
  it('acknowledges cancel without marking active work cancelled', async () => {
    serverJobs = [job({ status: 'downloading' })]
    const queue = useQueueStore()
    await queue.refresh()
    vi.mocked(jobsApi.cancelJob).mockImplementation(async (id) => {
      serverJobs = [job({ id, status: 'downloading', cancel_requested_at: '2026-10-03T00:00:01Z' })]
      return serverJobs[0]
    })
    await queue.actOnJob(job().id, 'cancel')
    expect(queue.jobs[0].status).toBe('downloading')
    expect(queue.jobs[0].cancel_requested_at).not.toBeNull()
    expect(queue.busyJobs).toEqual({})
  })
  it('retries failed work and updates from backend response', async () => {
    serverJobs = [job({ status: 'failed', attempt_count: 1 })]
    const queue = useQueueStore()
    await queue.refresh()
    vi.mocked(jobsApi.retryJob).mockImplementation(async () => {
      serverJobs = [job({ attempt_count: 1 })]
      return serverJobs[0]
    })
    await queue.actOnJob(job().id, 'retry')
    expect(queue.jobs[0].status).toBe('queued')
    expect(queue.jobs[0].attempt_count).toBe(1)
  })
  it('refreshes server truth on an action conflict', async () => {
    const queue = useQueueStore()
    await queue.refresh()
    serverJobs = [job({ status: 'completed', progress_percent: 100 })]
    vi.mocked(jobsApi.cancelJob).mockRejectedValueOnce(
      new ApiError('Only running jobs can be cancelled', 'CONFLICT', 409),
    )
    vi.mocked(jobsApi.fetchJob).mockResolvedValueOnce(serverJobs[0])
    await queue.actOnJob(job().id, 'cancel')
    expect(queue.jobs[0].status).toBe('completed')
    expect(queue.jobErrors[job().id]).toContain('cancelled')
  })
  it('keeps other jobs actionable during one pending mutation', async () => {
    serverJobs = [job(), job({ id: 'two' })]
    const queue = useQueueStore()
    await queue.refresh()
    let finish!: (value: Job) => void
    vi.mocked(jobsApi.cancelJob).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const pending = queue.actOnJob(job().id, 'cancel')
    await queue.actOnJob(job().id, 'cancel')
    expect(jobsApi.cancelJob).toHaveBeenCalledTimes(1)
    expect(queue.busyJobs.two).toBeUndefined()
    finish(job({ status: 'cancelled' }))
    await pending
  })
  it('keeps pause state on failure and changes it only on success', async () => {
    const queue = useQueueStore()
    await queue.refresh()
    vi.mocked(queueApi.pauseQueue).mockRejectedValueOnce(
      new ApiError('Pause failed', 'HTTP_ERROR', 500),
    )
    await queue.setPaused(true)
    expect(queue.paused).toBe(false)
    expect(queue.controlError).toBe('Pause failed')
    await queue.setPaused(true)
    expect(queue.paused).toBe(true)
    await queue.setPaused(false)
    expect(queue.paused).toBe(false)
  })
})

describe('polling ownership', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  it('uses one timer, polls active work and stops cleanly', async () => {
    const queue = useQueueStore()
    queue.startPolling('queue')
    queue.startPolling('queue')
    await flushPromises()
    expect(queueApi.fetchQueueState).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS)
    expect(queueApi.fetchQueueState).toHaveBeenCalledTimes(2)
    queue.stopPolling()
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(IDLE_POLL_MS)
    expect(queueApi.fetchQueueState).toHaveBeenCalledTimes(2)
  })
  it('slows polling for terminal work and failures', async () => {
    serverJobs = [job({ status: 'completed' })]
    const queue = useQueueStore()
    queue.startPolling('queue')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS)
    expect(queueApi.fetchQueueState).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(IDLE_POLL_MS - ACTIVE_POLL_MS)
    expect(queueApi.fetchQueueState).toHaveBeenCalledTimes(2)
  })
  it('does not overlap reads and aborts stale results after unmount', async () => {
    let resolve!: (value: JobPage) => void
    vi.mocked(jobsApi.fetchJobs).mockImplementationOnce(
      () =>
        new Promise((yes) => {
          resolve = yes
        }),
    )
    const queue = useQueueStore()
    queue.startPolling('queue')
    const pending = queue.refresh()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(IDLE_POLL_MS)
    expect(jobsApi.fetchJobs).toHaveBeenCalledTimes(1)
    queue.stopPolling()
    expect(vi.mocked(jobsApi.fetchJobs).mock.calls[0][1]?.aborted).toBe(true)
    resolve(jobPage(serverJobs))
    await pending
    expect(queue.jobs).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
    expect(jobsApi.fetchJobs).toHaveBeenCalledTimes(1)
  })
  it('cleans timers on real page unmount and reloads pause state on remount', async () => {
    const pinia = createPinia()
    const wrapper = mount(QueueView, { global: { plugins: [pinia], stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain('Currently running jobs continue')
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
    serverPaused = true
    const reloaded = mount(QueueView, {
      global: { plugins: [createPinia()], stubs: { RouterLink: true } },
    })
    await flushPromises()
    expect(reloaded.text()).toContain('Queue paused')
    reloaded.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('keeps one timer across router navigation even when an old read finishes late', async () => {
    let finishOldRead!: (value: JobPage) => void
    vi.mocked(jobsApi.fetchJobs).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOldRead = resolve
        }),
    )
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/queue')
    const wrapper = mount(RouterView, { global: { plugins: [createPinia(), router] } })
    try {
      await flushPromises()
      const oldSignal = vi.mocked(jobsApi.fetchJobs).mock.calls[0][1]
      await router.push('/download')
      await flushPromises()
      expect(oldSignal?.aborted).toBe(true)
      expect(vi.getTimerCount()).toBe(0)
      await router.push('/')
      await flushPromises()
      expect(vi.getTimerCount()).toBe(1)
      finishOldRead(jobPage([job({ id: 'stale-job' })]))
      await flushPromises()
      expect(vi.getTimerCount()).toBe(1)
      expect(useQueueStore().recentJobs.map((row) => row.id)).toEqual([job().id])
      for (const path of ['/queue', '/', '/queue', '/']) {
        await router.push(path)
        await flushPromises()
        expect(vi.getTimerCount()).toBe(1)
      }
      const reads = vi.mocked(queueApi.fetchQueueState).mock.calls.length
      await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS)
      expect(queueApi.fetchQueueState).toHaveBeenCalledTimes(reads + 1)
      await router.push('/download')
      await flushPromises()
      expect(vi.getTimerCount()).toBe(0)
      await vi.advanceTimersByTimeAsync(IDLE_POLL_MS)
      expect(queueApi.fetchQueueState).toHaveBeenCalledTimes(reads + 1)
    } finally {
      wrapper.unmount()
    }
  })
  it('preserves cached jobs while offline and automatically recovers with one polling timer', async () => {
    const queue = useQueueStore()
    queue.startPolling('queue')
    await flushPromises()
    vi.mocked(jobsApi.fetchJobs).mockRejectedValue(new ApiError('Cannot connect', 'NETWORK_ERROR'))
    await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS)
    expect(queue.jobs).toEqual(serverJobs)
    expect(queue.error).toBe('Cannot connect')
    expect(vi.getTimerCount()).toBe(1)
    const reads = vi.mocked(queueApi.fetchQueueState).mock.calls.length
    await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS)
    expect(queueApi.fetchQueueState).toHaveBeenCalledTimes(reads)
    serverJobs = [job({ status: 'downloading', progress_percent: 30 })]
    vi.mocked(jobsApi.fetchJobs).mockImplementation(async (query: JobQuery = {}) =>
      jobPage(serverJobs, query),
    )
    await vi.advanceTimersByTimeAsync(IDLE_POLL_MS - ACTIVE_POLL_MS)
    expect(queueApi.fetchQueueState).toHaveBeenCalledTimes(reads + 1)
    expect(queue.error).toBeNull()
    expect(queue.jobs[0].progress_percent).toBe(30)
    expect(vi.getTimerCount()).toBe(1)
    queue.stopPolling()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('fetches the latest five jobs across partial last pages for Dashboard', async () => {
    serverJobs = Array.from({ length: 12 }, (_, i) => job({ id: String(i), status: 'completed' }))
    const wrapper = mount(DashboardView, {
      global: { plugins: [createPinia()], stubs: { RouterLink: true } },
    })
    await flushPromises()
    expect(useQueueStore().recentJobs.map((row) => row.id)).toEqual(['11', '10', '9', '8', '7'])
    wrapper.unmount()
  })
})
