import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '../api/library'
import { errorMessage } from '../api/client'
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
    detailController: AbortController | null = null
  async function load(value = page.value): Promise<void> {
    listController?.abort()
    const controller = new AbortController()
    listController = controller
    loading.value = true
    try {
      const result = await api.fetchLibrary(filters.value, value, controller.signal)
      if (listController !== controller) return
      items.value = result.items
      page.value = result.page
      total.value = result.total
      error.value = null
    } catch (failure) {
      if (!controller.signal.aborted) error.value = errorMessage(failure)
    } finally {
      if (listController === controller) loading.value = false
    }
  }
  async function organizations(): Promise<void> {
    try {
      ;[tags.value, collections.value] = await Promise.all([
        api.fetchNamed('tags'),
        api.fetchNamed('collections'),
      ])
    } catch (failure) {
      actionError.value = errorMessage(failure)
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
      if (detailController === controller) selected.value = result
    } catch (failure) {
      if (!controller.signal.aborted) actionError.value = errorMessage(failure)
    }
  }
  async function action(operation: DeleteOperation | 'force'): Promise<void> {
    if (!selected.value || busy.value) return
    const id = selected.value.id
    busy.value = true
    actionError.value = null
    notice.value = null
    try {
      if (operation === 'force') {
        const result = await api.forceRedownload(id)
        notice.value = `${result.jobs.length} redownload job queued. View Queue to follow progress.`
      } else {
        const result = await api.destroyVideo(id, operation)
        if (selected.value?.id === id) selected.value = result
        await load()
      }
    } catch (failure) {
      actionError.value = errorMessage(failure)
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
    busy.value = true
    actionError.value = null
    try {
      if (name) itemId = (await api.createNamed(kind, name)).id
      const result = await api.attachNamed(kind, id, itemId, remove)
      if (selected.value?.id === id) selected.value = result
      await organizations()
      await load()
    } catch (failure) {
      actionError.value = errorMessage(failure)
    } finally {
      busy.value = false
    }
  }
  function stop(): void {
    listController?.abort()
    detailController?.abort()
    listController = null
    detailController = null
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
