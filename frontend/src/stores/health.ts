import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchHealth } from '../api/health'

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

  return { status, check }
})
