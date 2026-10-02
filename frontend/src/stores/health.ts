import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchHealth } from '../api/health'
import { ApiError } from '../api/client'

export const useHealthStore = defineStore('health', () => {
  const status = ref<'idle' | 'checking' | 'reachable' | 'unreachable'>('idle')

  async function check(): Promise<void> {
    if (status.value === 'checking') return
    status.value = 'checking'
    try {
      await fetchHealth()
      status.value = 'reachable'
    } catch {
      status.value = 'unreachable'
    }
  }

  function observe(failure?: unknown): void {
    status.value =
      failure instanceof ApiError &&
      (failure.status === null ||
        failure.code === 'HTTP_ERROR' ||
        failure.code === 'INVALID_RESPONSE')
        ? 'unreachable'
        : 'reachable'
  }
  return { status, check, observe }
})
