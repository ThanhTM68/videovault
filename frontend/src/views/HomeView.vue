<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useHealthStore } from '../stores/health'

const health = useHealthStore()
const label = computed(() => ({
  idle: 'Backend status has not been checked.',
  checking: 'Checking backend…',
  reachable: 'Backend reachable',
  unreachable: 'Backend unreachable. Start the backend and try again.',
})[health.status])

onMounted(() => { void health.check() })
</script>

<template>
  <section aria-labelledby="connection-title">
    <h2 id="connection-title">Connection</h2>
    <p role="status" aria-live="polite">{{ label }}</p>
    <button :disabled="health.status === 'checking'" @click="health.check()">
      Check again
    </button>
  </section>
</template>
