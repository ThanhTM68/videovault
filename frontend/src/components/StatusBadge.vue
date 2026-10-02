<script setup lang="ts">
import type { JobStatus } from '../types/jobs'
import { STATUS_LABELS } from '../utils/jobs'
defineProps<{ status: JobStatus }>()
</script>

<template>
  <span class="badge" :class="`status-${status}`">{{ STATUS_LABELS[status] }}</span>
</template>
