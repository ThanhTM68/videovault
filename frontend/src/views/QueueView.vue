<script setup lang="ts">
import { computed } from 'vue'
import JobCard from '../components/JobCard.vue'
import { useQueuePolling } from '../composables/useQueuePolling'
import { JOB_STATUSES, type JobStatus } from '../types/jobs'
import { PAGE_SIZE } from '../stores/queue'
import { formatDate, STATUS_LABELS } from '../utils/jobs'
const queue = useQueuePolling('queue')
const pages = computed(() => Math.max(1, Math.ceil(queue.total / PAGE_SIZE)))
function changeFilter(event: Event): void {
  const value = (event.target as HTMLSelectElement).value as JobStatus | ''
  void queue.setFilter(value)
}
</script>

<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">Download management</p>
      <h2>Queue</h2>
      <p class="muted">Monitor progress and manage your jobs.</p>
    </div>
    <RouterLink class="button-link" to="/download">Add videos</RouterLink>
  </div>
  <section class="panel queue-toolbar">
    <div>
      <span class="badge">{{
        queue.paused === null
          ? 'Queue state unavailable'
          : queue.paused
            ? 'Queue paused'
            : queue.hasWork
              ? 'Queue active'
              : 'Ready for jobs'
      }}</span>
      <p class="muted small">
        Pause stops new jobs from starting. Currently running jobs continue.
      </p>
    </div>
    <div class="toolbar-actions">
      <button
        :disabled="queue.paused === null || queue.controlBusy"
        @click="queue.setPaused(!queue.paused)"
      >
        {{
          queue.controlBusy ? 'Updating…' : queue.paused ? 'Resume Queue' : 'Pause Queue'
        }}</button
      ><button class="button-secondary" :disabled="queue.loading" @click="queue.refresh(true)">
        {{ queue.loading ? 'Refreshing…' : 'Refresh' }}
      </button>
    </div>
  </section>
  <p v-if="queue.controlError" role="alert" class="error-panel">{{ queue.controlError }}</p>
  <p v-if="queue.error" role="alert" class="error-panel">
    {{ queue.error }} <span v-if="queue.loaded">Showing the last loaded jobs.</span>
  </p>
  <div class="list-toolbar">
    <div>
      <label for="status-filter">Status</label
      ><select id="status-filter" :value="queue.statusFilter" @change="changeFilter">
        <option value="">All statuses</option>
        <option v-for="status in JOB_STATUSES" :key="status" :value="status">
          {{ STATUS_LABELS[status] }}
        </option>
      </select>
    </div>
    <p class="muted small">
      {{ queue.total }} jobs · oldest first<span v-if="queue.lastUpdated">
        · Updated {{ formatDate(queue.lastUpdated) }}</span
      >
    </p>
  </div>
  <section class="panel" aria-label="Jobs">
    <p v-if="queue.loading && !queue.loaded" role="status">Loading jobs…</p>
    <p v-else-if="!queue.jobs.length && !queue.error" class="empty-state">
      {{ queue.statusFilter ? 'No jobs with this status.' : 'No download jobs yet.' }}
      <RouterLink to="/download">Add video URLs from Quick Download.</RouterLink>
    </p>
    <JobCard
      v-for="job in queue.jobs"
      :key="job.id"
      :job="job"
      :busy="queue.busyJobs[job.id]"
      :action-error="queue.jobErrors[job.id]"
      @cancel="queue.actOnJob($event, 'cancel')"
      @retry="queue.actOnJob($event, 'retry')"
    />
  </section>
  <nav v-if="queue.total > PAGE_SIZE" class="pagination" aria-label="Job pages">
    <button
      class="button-secondary"
      :disabled="queue.page === 1 || queue.loading"
      @click="queue.setPage(queue.page - 1)"
    >
      Previous</button
    ><span>Page {{ queue.page }} of {{ pages }}</span
    ><button
      class="button-secondary"
      :disabled="queue.page >= pages || queue.loading"
      @click="queue.setPage(queue.page + 1)"
    >
      Next
    </button>
  </nav>
</template>
