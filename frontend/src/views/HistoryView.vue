<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useHistoryStore } from '../stores/history'
import { PLATFORMS, type Platform } from '../types/library'
import type { JobStatus } from '../types/jobs'
import { formatDate } from '../utils/jobs'
import StatusBadge from '../components/StatusBadge.vue'
import { requestedOptions } from '../utils/history'
const history = useHistoryStore(),
  platform = ref<Platform | ''>(''),
  status = ref<JobStatus | ''>('')
function apply(): void {
  history.filters = { platform: platform.value || undefined, status: status.value || undefined }
  void history.load(1)
}
onMounted(() => {
  history.filters = {}
  void history.load(1)
})
onUnmounted(() => {
  history.stop()
})
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">Download events</p>
      <h2>History</h2>
      <p class="muted">Actual media execution attempts. Duplicate skips remain in Queue.</p>
    </div>
    <RouterLink to="/library">View Library</RouterLink>
  </div>
  <form class="panel library-filters" @submit.prevent="apply">
    <div>
      <label for="history-platform">Platform</label
      ><select id="history-platform" v-model="platform">
        <option value="">All platforms</option>
        <option v-for="value in PLATFORMS" :key="value" :value="value">{{ value }}</option>
      </select>
    </div>
    <div>
      <label for="history-status">Status</label
      ><select id="history-status" v-model="status">
        <option value="">All statuses</option>
        <option
          v-for="value in ['downloading', 'completed', 'failed', 'cancelled']"
          :key="value"
          :value="value"
        >
          {{ value }}
        </option>
      </select>
    </div>
    <button :disabled="history.loading">Search</button
    ><button
      type="button"
      class="button-secondary"
      :disabled="history.loading"
      @click="history.load()"
    >
      Refresh
    </button>
  </form>
  <p v-if="history.error" role="alert" class="error-panel">
    {{ history.error }} Previously loaded history is kept.
  </p>
  <section class="panel">
    <p v-if="history.loading && !history.items.length" role="status">Loading history…</p>
    <p v-else-if="!history.items.length && !history.error" class="empty-state">
      No download history yet.
    </p>
    <article v-for="item in history.items" :key="item.id" class="job-card">
      <div>
        <StatusBadge :status="item.status" />
        <h3>{{ item.title || 'Untitled video' }}</h3>
        <p>
          {{ item.platform }} · {{ item.forced ? 'Forced redownload' : 'Normal download' }} ·
          Attempt {{ item.attempt_number ?? 'unknown' }}
        </p>
        <p class="muted small">
          Created {{ formatDate(item.created_at) }} · Started {{ formatDate(item.started_at) }} ·
          Finished {{ formatDate(item.completed_at) }}
        </p>
        <p v-if="item.failure_code" class="error">
          {{ item.failure_code }} · {{ item.failure_message }}
        </p>
        <details>
          <summary>Requested options</summary>
          <p>{{ requestedOptions(item.requested_quality) }}</p>
        </details>
      </div>
    </article>
  </section>
  <nav class="pagination" aria-label="History pages">
    <button
      :disabled="history.page <= 1 || history.loading"
      @click="history.load(history.page - 1)"
    >
      Previous</button
    ><span
      >Page {{ history.page }} of {{ Math.max(1, Math.ceil(history.total / 25)) }} ·
      {{ history.total }} events</span
    ><button
      :disabled="history.page * 25 >= history.total || history.loading"
      @click="history.load(history.page + 1)"
    >
      Next
    </button>
  </nav>
</template>
