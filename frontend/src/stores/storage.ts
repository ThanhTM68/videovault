import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '../api/storage'
import { errorMessage } from '../api/client'
import type { StorageStatus } from '../types/storage'
import { useHealthStore } from './health'
export const useStorageStore = defineStore('storage', () => {
  const status = ref<StorageStatus | null>(null)
  const loading = ref(false),
    busy = ref(false),
    error = ref<string | null>(null)
  const authorizationUrl = ref<string | null>(null)
  const drive = computed(() =>
    status.value?.providers.find((item) => item.provider === 'google_drive'),
  )
  const driveReady = computed(() => !!drive.value?.available && !error.value && !busy.value)
  let controller: AbortController | null = null
  let lifecycleVersion = 0
  let active = false
  async function load(): Promise<void> {
    if (loading.value || busy.value) return
    const current = new AbortController()
    controller = current
    const version = lifecycleVersion
    loading.value = true
    try {
      const result = await api.fetchStorage(current.signal)
      if (version !== lifecycleVersion || current.signal.aborted) return
      status.value = result
      error.value = null
      useHealthStore().observe()
    } catch (failure) {
      if (version !== lifecycleVersion || current.signal.aborted) return
      error.value = errorMessage(failure)
      useHealthStore().observe(failure)
    } finally {
      current.abort()
      if (controller === current) {
        controller = null
        loading.value = false
      }
    }
  }
  function stop(owner?: number): void {
    if (owner !== undefined && owner !== lifecycleVersion) return
    active = false
    lifecycleVersion++
    controller?.abort()
    controller = null
    loading.value = false
    authorizationUrl.value = null
  }
  function start(): number {
    stop()
    active = true
    void load()
    return lifecycleVersion
  }
  async function action(kind: 'connect' | 'disconnect' | 'root', folderId?: string): Promise<void> {
    if (busy.value || loading.value) return
    const version = lifecycleVersion
    let current: AbortController | null = null
    busy.value = true
    error.value = null
    authorizationUrl.value = null
    try {
      if (kind === 'connect') {
        const result = await api.connectDrive()
        if (version !== lifecycleVersion) return
        authorizationUrl.value = result.authorization_url
      } else if (kind === 'disconnect') {
        const result = await api.disconnectDrive()
        if (version !== lifecycleVersion) return
        status.value = result
      } else {
        await api.setDriveRoot(folderId)
        if (version !== lifecycleVersion) return
        current = new AbortController()
        controller = current
        const result = await api.fetchStorage(current.signal)
        if (version !== lifecycleVersion || current.signal.aborted) return
        status.value = result
      }
      useHealthStore().observe()
    } catch (failure) {
      if (version !== lifecycleVersion || current?.signal.aborted) return
      error.value = errorMessage(failure)
      useHealthStore().observe(failure)
    } finally {
      current?.abort()
      if (current && controller === current) controller = null
      busy.value = false
      if (active && version !== lifecycleVersion) void load()
    }
  }
  return {
    status,
    loading,
    busy,
    error,
    authorizationUrl,
    drive,
    driveReady,
    load,
    action,
    start,
    stop,
  }
})
