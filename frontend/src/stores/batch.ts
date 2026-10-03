import { ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, errorMessage } from '../api/client'
import * as api from '../api/sources'
import type { DownloadOptions } from '../types/api'
import type {
  BatchResult,
  SourceCapabilities,
  SourcePreview,
  SourceRequest,
} from '../types/sources'

export const useBatchStore = defineStore('batch', () => {
  const preview = ref<SourcePreview | null>(null)
  const capabilities = ref<SourceCapabilities | null>(null)
  const selectedIds = ref<string[]>([])
  const loading = ref(false),
    submitting = ref(false),
    valid = ref(false)
  const error = ref<string | null>(null),
    result = ref<BatchResult | null>(null)
  let controller: AbortController | null = null
  let version = 0
  function invalidate(sourceChanged = false): void {
    version++
    controller?.abort()
    controller = null
    loading.value = false
    valid.value = false
    preview.value = null
    selectedIds.value = []
    error.value = null
    result.value = null
    if (sourceChanged) capabilities.value = null
  }
  async function load(criteria: SourceRequest): Promise<void> {
    if (submitting.value || loading.value) return
    invalidate()
    const current = new AbortController(),
      requestVersion = version
    controller = current
    loading.value = true
    try {
      const response = await api.resolveSource(criteria, current.signal)
      if (current.signal.aborted || requestVersion !== version) return
      preview.value = response
      capabilities.value = response.source.capabilities
      valid.value = true
    } catch (failure) {
      if (!current.signal.aborted && requestVersion === version) error.value = errorMessage(failure)
    } finally {
      if (requestVersion === version) {
        loading.value = false
        controller = null
      }
    }
  }
  function eligible(id: string, force: boolean): boolean {
    const item = preview.value?.candidates.find((item) => item.platform_video_id === id)
    return valid.value && !!item && (force || !item.has_download_history)
  }
  function select(id: string, value: boolean, force: boolean): void {
    if (submitting.value || !eligible(id, force)) return
    selectedIds.value = selectedIds.value.filter((item) => item !== id)
    if (value) selectedIds.value.push(id)
  }
  function selectAll(force: boolean): void {
    if (submitting.value) return
    selectedIds.value =
      preview.value?.candidates
        .filter((item) => eligible(item.platform_video_id, force))
        .map((item) => item.platform_video_id) ?? []
  }
  function clear(): void {
    if (!submitting.value) selectedIds.value = []
  }
  function syncForce(force: boolean): void {
    selectedIds.value = selectedIds.value.filter((id) => eligible(id, force))
  }
  async function submit(options: DownloadOptions): Promise<void> {
    if (submitting.value || loading.value || !valid.value || !preview.value) return
    syncForce(options.force ?? false)
    if (!selectedIds.value.length) return
    submitting.value = true
    const submissionVersion = version
    error.value = null
    result.value = null
    try {
      const response = await api.submitBatch({
        ...options,
        preview_id: preview.value.preview_id,
        selected_ids: [...selectedIds.value],
      })
      if (submissionVersion !== version) return
      result.value = response
      valid.value = false
      selectedIds.value = []
    } catch (failure) {
      if (submissionVersion !== version) return
      error.value = errorMessage(failure)
      if (failure instanceof ApiError && failure.code === 'SOURCE_PREVIEW_EXPIRED') {
        valid.value = false
        selectedIds.value = []
      }
    } finally {
      submitting.value = false
    }
  }
  return {
    preview,
    capabilities,
    selectedIds,
    loading,
    submitting,
    valid,
    error,
    result,
    invalidate,
    load,
    eligible,
    select,
    selectAll,
    clear,
    syncForce,
    submit,
  }
})
