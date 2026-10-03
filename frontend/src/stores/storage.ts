import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '../api/storage'
import { errorMessage } from '../api/client'
import type { StorageStatus } from '../types/storage'
export const useStorageStore = defineStore('storage', () => {
  const status = ref<StorageStatus | null>(null)
  const loading = ref(false),
    busy = ref(false),
    error = ref<string | null>(null)
  const authorizationUrl = ref<string | null>(null)
  const drive = computed(() =>
    status.value?.providers.find((item) => item.provider === 'google_drive'),
  )
  const driveReady = computed(() => !!drive.value?.available && !error.value)
  async function load(): Promise<void> {
    if (loading.value || busy.value) return
    loading.value = true
    try {
      status.value = await api.fetchStorage()
      error.value = null
    } catch (failure) {
      error.value = errorMessage(failure)
    } finally {
      loading.value = false
    }
  }
  async function action(kind: 'connect' | 'disconnect' | 'root', folderId?: string): Promise<void> {
    if (busy.value || loading.value) return
    busy.value = true
    error.value = null
    authorizationUrl.value = null
    try {
      if (kind === 'connect') authorizationUrl.value = (await api.connectDrive()).authorization_url
      else if (kind === 'disconnect') status.value = await api.disconnectDrive()
      else {
        await api.setDriveRoot(folderId)
        status.value = await api.fetchStorage()
      }
    } catch (failure) {
      error.value = errorMessage(failure)
    } finally {
      busy.value = false
    }
  }
  return { status, loading, busy, error, authorizationUrl, drive, driveReady, load, action }
})
