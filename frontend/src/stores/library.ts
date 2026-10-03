import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '../api/library'
import { errorMessage } from '../api/client'
import { useHealthStore } from './health'
import type {
  LibraryVideo,
  LibraryFilters,
  VideoDetail,
  NamedItem,
  DeleteOperation,
} from '../types/library'

export const useLibraryStore = defineStore('library', () => {
  const items = ref<LibraryVideo[]>([]),
    selected = ref<VideoDetail | null>(null)
  const tags = ref<NamedItem[]>([]),
    collections = ref<NamedItem[]>([])
  const page = ref(1),
    total = ref(0),
    filters = ref<LibraryFilters>({})
  const loading = ref(false),
    busy = ref(false),
    error = ref<string | null>(null)
  const actionError = ref<string | null>(null),
    notice = ref<string | null>(null)
  let listController: AbortController | null = null,
    detailController: AbortController | null = null,
    organizationController: AbortController | null = null
  let lifecycleVersion = 0
  async function load(value = page.value): Promise<void> {
    listController?.abort()
    const controller = new AbortController()
    listController = controller
    loading.value = true
    try {
      const criteria = { ...filters.value }
      let result = await api.fetchLibrary(criteria, value, controller.signal)
      if (listController !== controller) return
      const lastPage = Math.max(1, Math.ceil(result.total / result.page_size))
      if (result.page > lastPage) {
        result = await api.fetchLibrary(criteria, lastPage, controller.signal)
        if (listController !== controller) return
      }
      items.value = result.items
      page.value = result.page
      total.value = result.total
      error.value = null
      useHealthStore().observe()
    } catch (failure) {
      if (!controller.signal.aborted) {
        error.value = errorMessage(failure)
        useHealthStore().observe(failure)
      }
    } finally {
      if (listController === controller) loading.value = false
    }
  }
  async function organizations(): Promise<void> {
    organizationController?.abort()
    const controller = new AbortController()
    organizationController = controller
    const version = lifecycleVersion
    try {
      const result = await Promise.all([
        api.fetchNamed('tags', controller.signal),
        api.fetchNamed('collections', controller.signal),
      ])
      if (version !== lifecycleVersion || controller.signal.aborted) return
      ;[tags.value, collections.value] = result
      useHealthStore().observe()
    } catch (failure) {
      if (version === lifecycleVersion && !controller.signal.aborted) {
        actionError.value = errorMessage(failure)
        useHealthStore().observe(failure)
      }
    } finally {
      controller.abort()
      if (organizationController === controller) organizationController = null
    }
  }
  async function select(id: string): Promise<void> {
    detailController?.abort()
    const controller = new AbortController()
    detailController = controller
    selected.value = null
    actionError.value = null
    notice.value = null
    try {
      const result = await api.fetchDetail(id, controller.signal)
      if (detailController === controller) {
        selected.value = result
        useHealthStore().observe()
      }
    } catch (failure) {
      if (!controller.signal.aborted) {
        actionError.value = errorMessage(failure)
        useHealthStore().observe(failure)
      }
    }
  }
  async function action(operation: DeleteOperation | 'force' | 'refresh'): Promise<void> {
    if (!selected.value || busy.value) return
    const id = selected.value.id
    const version = lifecycleVersion
    busy.value = true
    actionError.value = null
    notice.value = null
    try {
      if (operation === 'force') {
        const result = await api.forceRedownload(id)
        if (version !== lifecycleVersion) return
        useHealthStore().observe()
        notice.value = `${result.jobs.length} redownload job queued. View Queue to follow progress.`
      } else {
        const result =
          operation === 'refresh'
            ? await api.refreshFiles(id)
            : await api.destroyVideo(id, operation)
        if (version !== lifecycleVersion) return
        useHealthStore().observe()
        if (selected.value?.id === id) selected.value = result
        await load()
      }
    } catch (failure) {
      if (version !== lifecycleVersion) return
      actionError.value = errorMessage(failure)
      useHealthStore().observe(failure)
      if (operation !== 'force') {
        detailController?.abort()
        const controller = new AbortController()
        detailController = controller
        try {
          const result = await api.fetchDetail(id, controller.signal)
          if (version !== lifecycleVersion || detailController !== controller) return
          useHealthStore().observe()
          if (selected.value?.id === id) selected.value = result
          await load()
        } catch {
          // Keep the operation error and last snapshot when reconciliation is unavailable.
        } finally {
          if (detailController === controller) detailController = null
          controller.abort()
        }
      }
    } finally {
      busy.value = false
    }
  }
  async function organize(
    kind: 'tags' | 'collections',
    itemId: string,
    remove = false,
    name?: string,
  ): Promise<void> {
    if (!selected.value || busy.value) return
    const id = selected.value.id
    const version = lifecycleVersion
    busy.value = true
    actionError.value = null
    try {
      if (name) itemId = (await api.createNamed(kind, name)).id
      if (version !== lifecycleVersion) return
      const result = await api.attachNamed(kind, id, itemId, remove)
      if (version !== lifecycleVersion) return
      useHealthStore().observe()
      if (selected.value?.id === id) selected.value = result
      await organizations()
      if (version !== lifecycleVersion) return
      await load()
    } catch (failure) {
      if (version === lifecycleVersion) {
        actionError.value = errorMessage(failure)
        useHealthStore().observe(failure)
      }
    } finally {
      busy.value = false
    }
  }
  function stop(): void {
    lifecycleVersion++
    listController?.abort()
    detailController?.abort()
    organizationController?.abort()
    listController = null
    detailController = null
    organizationController = null
    loading.value = false
  }
  return {
    items,
    selected,
    tags,
    collections,
    page,
    total,
    filters,
    loading,
    busy,
    error,
    actionError,
    notice,
    load,
    select,
    action,
    organize,
    organizations,
    stop,
  }
})
