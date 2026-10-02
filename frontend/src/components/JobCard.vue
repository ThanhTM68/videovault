<script setup lang="ts">
import { computed } from 'vue'
import type { Job } from '../types/jobs'
import { canCancel, canRetry, formatDate, isActive, stepLabel } from '../utils/jobs'
import StatusBadge from './StatusBadge.vue'
const props = defineProps<{
  job: Job
  compact?: boolean
  busy?: 'cancel' | 'retry'
  actionError?: string
}>()
defineEmits<{ cancel: [id: string]; retry: [id: string] }>()
const cancelling = computed(() => !!props.job.cancel_requested_at && isActive(props.job.status))
const progress = computed(() =>
  props.job.status === 'completed'
    ? 100
    : props.job.progress_percent !== null && props.job.progress_percent > 0
      ? props.job.progress_percent
      : null,
)
</script>

<template>
  <article class="job-card" :aria-label="`Job ${job.id}`">
    <div class="job-main">
      <div class="job-heading">
        <StatusBadge :status="job.status" /><span class="job-id">{{ job.id.slice(0, 8) }}</span
        ><span v-if="cancelling" class="muted">Cancelling…</span>
      </div>
      <p class="job-step">{{ stepLabel(job.current_step) }}</p>
      <div v-if="isActive(job.status) || job.status === 'completed'" class="progress-row">
        <progress
          v-if="progress !== null"
          :value="progress"
          max="100"
          :aria-label="`Job progress: ${Math.round(progress)} percent`"
        />
        <progress v-else aria-label="Job progress unknown" />
        <span v-if="progress !== null">{{ Math.round(progress) }}%</span
        ><span v-else class="muted">In progress</span>
      </div>
      <p v-if="job.error" class="job-error">
        <strong>{{ job.error.code }}</strong> · {{ job.error.message }}
      </p>
      <p v-if="actionError" role="alert" class="error">{{ actionError }}</p>
      <p class="job-meta">
        Created {{ formatDate(job.created_at) }} · Attempt {{ job.attempt_count }} /
        {{ job.max_attempts }}
      </p>
      <details v-if="!compact">
        <summary>Job details</summary>
        <dl class="details-grid">
          <dt>ID</dt>
          <dd>{{ job.id }}</dd>
          <dt>Type</dt>
          <dd>{{ job.type }}</dd>
          <dt>Started</dt>
          <dd>{{ formatDate(job.started_at) }}</dd>
          <dt>Finished</dt>
          <dd>{{ formatDate(job.completed_at) }}</dd>
          <dt>Cancel requested</dt>
          <dd>{{ formatDate(job.cancel_requested_at) }}</dd>
        </dl>
      </details>
    </div>
    <div v-if="!compact" class="job-actions">
      <button
        v-if="canCancel(job)"
        class="button-secondary"
        :disabled="!!busy"
        @click="$emit('cancel', job.id)"
      >
        {{ busy === 'cancel' ? 'Cancelling…' : 'Cancel' }}
      </button>
      <button v-if="canRetry(job)" :disabled="!!busy" @click="$emit('retry', job.id)">
        {{ busy === 'retry' ? 'Retrying…' : 'Retry' }}
      </button>
      <span v-if="job.status === 'failed' && !canRetry(job)" class="muted"
        >Attempt limit reached</span
      >
    </div>
  </article>
</template>
