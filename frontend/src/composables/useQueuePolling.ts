import { onMounted, onUnmounted } from 'vue'
import { useQueueStore, type QueueView } from '../stores/queue'

export function useQueuePolling(view: QueueView): ReturnType<typeof useQueueStore> {
  const queue = useQueueStore()
  onMounted(() => {
    queue.startPolling(view)
  })
  onUnmounted(() => {
    queue.stopPolling()
  })
  return queue
}
