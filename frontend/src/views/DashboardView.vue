<script setup lang="ts">
import { useQueuePolling } from '../composables/useQueuePolling'
import JobCard from '../components/JobCard.vue'
const queue = useQueuePolling('dashboard')
</script>

<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">Workspace overview</p>
      <h2>Dashboard</h2>
      <p class="muted">Your download queue at a glance.</p>
    </div>
    <RouterLink class="button-link" to="/download">Add videos</RouterLink>
  </div>
  <p v-if="queue.error" role="alert" class="error-panel">
    {{ queue.error }}
    <button class="button-secondary" :disabled="queue.loading" @click="queue.refresh(true)">
      Try again
    </button>
  </p>
  <div class="stats-grid" aria-label="Queue summary">
    <section
      v-for="key in ['queued', 'running', 'completed', 'failed'] as const"
      :key="key"
      class="stat-card"
    >
      <p>{{ key }}</p>
      <strong>{{ queue.counts ? queue.counts[key] : '—' }}</strong>
    </section>
  </div>
  <section class="panel">
    <div class="section-heading">
      <h3>Recent jobs</h3>
      <RouterLink to="/queue">View Queue →</RouterLink>
    </div>
    <p v-if="queue.loading && !queue.loaded" role="status">Loading jobs…</p>
    <p v-else-if="!queue.recentJobs.length && !queue.error" class="empty-state">
      No download jobs yet.
      <RouterLink to="/download">Add video URLs from Quick Download.</RouterLink>
    </p>
    <JobCard v-for="job in queue.recentJobs" :key="job.id" :job="job" compact />
  </section>
</template>
