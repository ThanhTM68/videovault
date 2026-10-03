import { onMounted, onUnmounted } from 'vue'
import { useStorageStore } from '../stores/storage'

export function useStorageStatus(): ReturnType<typeof useStorageStore> {
  const storage = useStorageStore()
  let owner: number | undefined
  onMounted(() => {
    owner = storage.start()
  })
  onUnmounted(() => {
    storage.stop(owner)
  })
  return storage
}
