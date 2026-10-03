import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as jobsApi from '../api/jobs'
import * as queueApi from '../api/queue'
import { ApiError, errorMessage } from '../api/client'
import type { Job, JobStatus, QueueCounts } from '../types/jobs'
import { ACTIVE_STATUSES, isActive } from '../utils/jobs'
import { useHealthStore } from './health'

export const ACTIVE_POLL_MS = 2000
export const IDLE_POLL_MS = 10000
export const PAGE_SIZE = 25
export type QueueView = 'queue' | 'dashboard'

export const useQueueStore = defineStore('queue', () => {
  const jobs = ref<Job[]>([])
  const recentJobs = ref<Job[]>([])
  const counts = ref<QueueCounts | null>(null)
  const total = ref(0)
  const page = ref(1)
  const statusFilter = ref<JobStatus | ''>('')
  const paused = ref<boolean | null>(null)
  const loading = ref(false)
  const queueLoaded = ref(false)
  const dashboardLoaded = ref(false)
  const mode = ref<QueueView>('queue')
  const loaded = computed(() =>
    mode.value === 'queue' ? queueLoaded.value : dashboardLoaded.value,
  )
  const error = ref<string | null>(null)
  const controlError = ref<string | null>(null)
  const controlBusy = ref(false)
  const busyJobs = ref<Record<string, 'cancel' | 'retry'>>({})
  const jobErrors = ref<Record<string, string>>({})
  const lastUpdated = ref<string | null>(null)
  const hasWork = computed(
    () =>
      (counts.value && counts.value.queued + counts.value.running > 0) ||
      (mode.value === 'queue' ? jobs.value : recentJobs.value).some(
        (job) => job.status === 'queued' || isActive(job.status),
      ),
  )
  let timer: ReturnType<typeof setTimeout> | null = null
  let polling = false
  let pollVersion = 0
  let readVersion = 0
  let controller: AbortController | null = null
  const recoveryReads = new Map<string, AbortController>()
  let pending: Promise<void> | null = null
  let lastCounts = Number.NEGATIVE_INFINITY

  function cancelRead(): void {
    readVersion++
    controller?.abort()
    controller = null
    pending = null
    loading.value = false
  }

  function refresh(forceCounts = false): Promise<void> {
    if (pending) return pending
    const current = new AbortController()
    controller = current
    const version = ++readVersion
    const view = mode.value
    loading.value = true
    const work = (async () => {
      try {
        const [state, first] = await Promise.all([
          queueApi.fetchQueueState(current.signal),
          jobsApi.fetchJobs(
            view === 'queue'
              ? { page: page.value, page_size: PAGE_SIZE, status: statusFilter.value || undefined }
              : { page: 1, page_size: 5 },
            current.signal,
          ),
        ])
        if (version !== readVersion || current.signal.aborted) return
        let result = first
        if (view === 'dashboard' && first.total > 5) {
          const lastPage = Math.ceil(first.total / 5)
          result = await jobsApi.fetchJobs({ page: lastPage, page_size: 5 }, current.signal)
          if (result.items.length < 5 && lastPage > 1) {
            const previous = await jobsApi.fetchJobs(
              { page: lastPage - 1, page_size: 5 },
              current.signal,
            )
            result = { ...result, items: [...previous.items, ...result.items].slice(-5) }
          }
        } else if (
          view === 'queue' &&
          first.page > Math.max(1, Math.ceil(first.total / PAGE_SIZE))
        ) {
          result = await jobsApi.fetchJobs(
            {
              page: Math.max(1, Math.ceil(first.total / PAGE_SIZE)),
              page_size: PAGE_SIZE,
              status: statusFilter.value || undefined,
            },
            current.signal,
          )
        }
        let summary: QueueCounts | null = null
        if (forceCounts || Date.now() - lastCounts >= IDLE_POLL_MS) {
          const statuses: JobStatus[] = ['queued', ...ACTIVE_STATUSES, 'completed', 'failed']
          const totals = await Promise.all(
            statuses.map((status) => jobsApi.fetchJobs({ status, page_size: 1 }, current.signal)),
          )
          summary = {
            queued: totals[0].total,
            running: totals.slice(1, 5).reduce((sum, item) => sum + item.total, 0),
            completed: totals[5].total,
            failed: totals[6].total,
          }
        }
        if (version !== readVersion || current.signal.aborted) return
        paused.value = state.paused
        if (view === 'queue') {
          jobs.value = result.items
          page.value = result.page
          total.value = result.total
          queueLoaded.value = true
        } else {
          recentJobs.value = [...result.items].reverse()
          dashboardLoaded.value = true
        }
        if (summary) {
          counts.value = summary
          lastCounts = Date.now()
        }
        lastUpdated.value = new Date().toISOString()
        error.value = null
        useHealthStore().observe()
      } catch (failure) {
        if (
          version !== readVersion ||
          current.signal.aborted ||
          (failure instanceof ApiError && failure.code === 'ABORTED')
        )
          return
        error.value = errorMessage(failure)
        useHealthStore().observe(failure)
      } finally {
        // Promise.all rejects before its siblings settle. Retire every fetch
        // owned by this cycle before releasing its controller or starting another.
        current.abort()
        if (version === readVersion) {
          loading.value = false
          pending = null
          controller = null
          schedulePoll()
        }
      }
    })()
    pending = work
    return work
  }

  function schedulePoll(): void {
    if (timer) clearTimeout(timer)
    timer = null
    if (!polling) return
    timer = setTimeout(
      () => {
        timer = null
        void refresh()
      },
      error.value || !hasWork.value ? IDLE_POLL_MS : ACTIVE_POLL_MS,
    )
  }
  function startPolling(view: QueueView): void {
    if (polling && mode.value === view) return
    stopPolling()
    mode.value = view
    polling = true
    pollVersion++
    void refresh()
  }
  function stopPolling(): void {
    polling = false
    pollVersion++
    if (timer) clearTimeout(timer)
    timer = null
    cancelRead()
    for (const read of recoveryReads.values()) read.abort()
    recoveryReads.clear()
  }
  async function setPage(value: number): Promise<void> {
    cancelRead()
    page.value = Math.max(1, value)
    await refresh()
  }
  async function setFilter(value: JobStatus | ''): Promise<void> {
    cancelRead()
    statusFilter.value = value
    page.value = 1
    await refresh()
  }
  function replaceJob(job: Job): void {
    jobs.value = jobs.value.map((row) => (row.id === job.id ? job : row))
    recentJobs.value = recentJobs.value.map((row) => (row.id === job.id ? job : row))
  }
  async function actOnJob(id: string, action: 'cancel' | 'retry'): Promise<void> {
    if (busyJobs.value[id]) return
    busyJobs.value = { ...busyJobs.value, [id]: action }
    delete jobErrors.value[id]
    const version = pollVersion
    try {
      const result = await (action === 'cancel' ? jobsApi.cancelJob(id) : jobsApi.retryJob(id))
      if (version !== pollVersion) return
      cancelRead()
      replaceJob(result)
      await refresh(true)
    } catch (failure) {
      if (version !== pollVersion) return
      jobErrors.value[id] = errorMessage(failure)
      useHealthStore().observe(failure)
      if (failure instanceof ApiError && failure.status === 409) {
        const read = new AbortController()
        recoveryReads.set(id, read)
        try {
          const result = await jobsApi.fetchJob(id, read.signal)
          if (version !== pollVersion || read.signal.aborted) return
          replaceJob(result)
        } catch {
          /* Keep last server snapshot. */
        } finally {
          read.abort()
          if (recoveryReads.get(id) === read) recoveryReads.delete(id)
        }
        if (version !== pollVersion) return
        cancelRead()
        await refresh(true)
      }
    } finally {
      delete busyJobs.value[id]
    }
  }
  async function setPaused(value: boolean): Promise<void> {
    if (controlBusy.value) return
    controlBusy.value = true
    controlError.value = null
    const version = pollVersion
    try {
      const result = await (value ? queueApi.pauseQueue() : queueApi.resumeQueue())
      if (version !== pollVersion) return
      cancelRead()
      paused.value = result.paused
      await refresh(true)
    } catch (failure) {
      if (version !== pollVersion) return
      controlError.value = errorMessage(failure)
      useHealthStore().observe(failure)
    } finally {
      controlBusy.value = false
    }
  }
  return {
    jobs,
    recentJobs,
    counts,
    total,
    page,
    statusFilter,
    paused,
    loading,
    loaded,
    error,
    controlError,
    controlBusy,
    busyJobs,
    jobErrors,
    lastUpdated,
    hasWork,
    refresh,
    startPolling,
    stopPolling,
    setPage,
    setFilter,
    actOnJob,
    setPaused,
  }
})
