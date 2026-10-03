import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchHistory } from '../api/library'
import { errorMessage } from '../api/client'
import { useHealthStore } from './health'
import type { HistoryItem, Platform } from '../types/library'

export const useHistoryStore = defineStore('history', () => {
  const items = ref<HistoryItem[]>([]),
    page = ref(1),
    total = ref(0),
    loading = ref(false)
  const error = ref<string | null>(null),
    filters = ref<{ platform?: Platform; status?: HistoryItem['status'] }>({})
  let controller: AbortController | null = null
  async function load(value = page.value): Promise<void> {
    controller?.abort()
    const current = new AbortController()
    controller = current
    loading.value = true
    try {
      const criteria = { ...filters.value }
      let result = await fetchHistory(value, criteria, current.signal)
      if (current !== controller) return
      const lastPage = Math.max(1, Math.ceil(result.total / result.page_size))
      if (result.page > lastPage) {
        result = await fetchHistory(lastPage, criteria, current.signal)
        if (current !== controller) return
      }
      items.value = result.items
      page.value = result.page
      total.value = result.total
      error.value = null
      useHealthStore().observe()
    } catch (failure) {
      if (!current.signal.aborted) {
        error.value = errorMessage(failure)
        useHealthStore().observe(failure)
      }
    } finally {
      if (current === controller) loading.value = false
    }
  }
  function stop(): void {
    controller?.abort()
    controller = null
    loading.value = false
  }
  return { items, page, total, loading, error, filters, load, stop }
})
