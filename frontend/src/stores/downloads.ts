import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '../api/downloads'
import { ApiError, errorMessage } from '../api/client'
import type { DownloadSubmissionRequest, VideoPreview } from '../types/api'
import { useHealthStore } from './health'

export const useDownloadsStore = defineStore('downloads', () => {
  const submitting = ref(false)
  const error = ref<string | null>(null)
  const createdIds = ref<string[]>([])
  const preview = ref<VideoPreview | null>(null)
  const previewLoading = ref(false)
  const previewError = ref<string | null>(null)
  let previewController: AbortController | null = null

  async function submit(body: DownloadSubmissionRequest): Promise<void> {
    if (submitting.value) return
    submitting.value = true
    error.value = null
    createdIds.value = []
    try {
      createdIds.value = (await api.submitDownloads(body)).jobs.map((job) => job.id)
      useHealthStore().observe()
    } catch (failure) {
      error.value = errorMessage(failure)
      useHealthStore().observe(failure)
    } finally {
      submitting.value = false
    }
  }
  function clearPreview(): void {
    previewController?.abort()
    previewController = null
    preview.value = null
    previewError.value = null
    previewLoading.value = false
  }
  async function loadPreview(url: string): Promise<void> {
    clearPreview()
    const controller = new AbortController()
    previewController = controller
    previewLoading.value = true
    try {
      const result = await api.resolvePreview(url, controller.signal)
      if (previewController === controller) {
        preview.value = result
        useHealthStore().observe()
      }
    } catch (failure) {
      if (
        previewController === controller &&
        !(failure instanceof ApiError && failure.code === 'ABORTED')
      ) {
        previewError.value = errorMessage(failure)
        useHealthStore().observe(failure)
      }
    } finally {
      if (previewController === controller) previewLoading.value = false
    }
  }
  return {
    submitting,
    error,
    createdIds,
    preview,
    previewLoading,
    previewError,
    submit,
    loadPreview,
    clearPreview,
  }
})
