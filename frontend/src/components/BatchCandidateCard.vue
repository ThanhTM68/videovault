<script setup lang="ts">
import { computed, ref } from 'vue'
import type { BatchCandidate } from '../types/sources'
import { safeImageUrl } from '../utils/download'
const props = defineProps<{ candidate: BatchCandidate; selected: boolean; disabled: boolean }>()
const emit = defineEmits<{ select: [value: boolean] }>()
const failed = ref(false)
const image = computed(() => (failed.value ? null : safeImageUrl(props.candidate.thumbnail_url)))
</script>
<template>
  <article class="panel library-card batch-card">
    <span v-if="candidate.has_download_history" class="badge">Already downloaded</span>
    <img
      v-if="image"
      :src="image"
      alt="Video thumbnail"
      loading="lazy"
      referrerpolicy="no-referrer"
      @error="failed = true"
    />
    <div v-else class="thumbnail-fallback">No thumbnail available</div>
    <label class="checkbox-label">
      <input
        type="checkbox"
        :checked="selected"
        :disabled="disabled"
        :aria-label="`Select ${candidate.title ?? candidate.platform_video_id}`"
        @change="emit('select', ($event.target as HTMLInputElement).checked)"
      />
      {{ candidate.platform_video_id }}
    </label>
    <h3>{{ candidate.title ?? 'Title unavailable' }}</h3>
    <p>{{ candidate.creator ?? 'Creator unavailable' }}</p>
    <p class="muted small">
      {{
        candidate.duration_seconds === null
          ? 'Duration unknown'
          : `${candidate.duration_seconds} seconds`
      }}
    </p>
    <p class="muted small">
      {{ candidate.upload_date ?? 'Date unknown' }} ·
      {{
        candidate.view_count === null
          ? 'Views unknown'
          : `${candidate.view_count.toLocaleString()} public views`
      }}
    </p>
    <p class="small">
      Successful history: {{ candidate.has_download_history ? 'Yes' : 'No' }} · Stored file
      (last-known): {{ candidate.has_file ? 'Yes' : 'No' }}
    </p>
  </article>
</template>
