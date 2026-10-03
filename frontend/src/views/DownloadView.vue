<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useStorageStatus } from '../composables/useStorageStatus'
import type { StorageProvider } from '../types/storage'
import { useDownloadsStore } from '../stores/downloads'
import { MAX_URLS, parseUrls, safeImageUrl, validateUrls } from '../utils/download'
const downloads = useDownloadsStore()
const storage = useStorageStatus()
const target = ref<StorageProvider>('local')
const targetReady = computed(
  () =>
    !!storage.status &&
    !storage.error &&
    !storage.loading &&
    !!storage.status.providers.find((item) => item.provider === target.value)?.available &&
    (target.value === 'local' || storage.driveReady),
)
let defaultApplied = false
watch(
  () => storage.status?.default_target,
  (value) => {
    if (value && !defaultApplied) {
      target.value = value
      defaultApplied = true
    }
  },
  { immediate: true },
)
const text = ref('')
const maxHeight = ref<1080 | 720 | 480>(1080)
const container = ref<'mp4' | 'mkv' | 'webm'>('mp4')
const audio = ref(true)
const force = ref(false)
const validation = ref<string | null>(null)
const imageFailed = ref(false)
const urls = computed(() => parseUrls(text.value))
const thumbnail = computed(() =>
  imageFailed.value ? null : safeImageUrl(downloads.preview?.thumbnail_url ?? null),
)
watch(text, () => {
  downloads.clearPreview()
  validation.value = null
  imageFailed.value = false
})
onUnmounted(() => {
  downloads.clearPreview()
})
async function submit(): Promise<void> {
  validation.value = validateUrls(urls.value)
  if (validation.value) return
  if (!targetReady.value) return
  await downloads.submit({
    urls: urls.value,
    max_height: maxHeight.value,
    preferred_container: container.value,
    audio_enabled: audio.value,
    storage_target: target.value,
    ...(force.value ? { force: true } : {}),
  })
}
async function preview(): Promise<void> {
  validation.value = validateUrls(urls.value)
  if (!validation.value && urls.value.length === 1) await downloads.loadPreview(urls.value[0])
}
</script>

<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">Add to your queue</p>
      <h2>Quick Download</h2>
      <p class="muted">Paste individual video links. Choose quality. Queue your downloads.</p>
    </div>
  </div>
  <div class="download-layout">
    <form class="panel" @submit.prevent="submit">
      <label for="video-urls">Video URLs</label
      ><textarea
        id="video-urls"
        v-model="text"
        rows="7"
        placeholder="https://www.youtube.com/watch?v=…&#10;https://www.tiktok.com/@…/video/…"
        :aria-invalid="!!validation"
        aria-describedby="url-help"
      />
      <div class="field-help">
        <p id="url-help">
          One URL per line · up to {{ MAX_URLS }}. Empty and repeated lines are ignored.
        </p>
        <span>{{ urls.length }} URL{{ urls.length === 1 ? '' : 's' }}</span>
      </div>
      <p v-if="validation" role="alert" class="error">{{ validation }}</p>
      <div class="options-grid">
        <div>
          <label for="max-height">Maximum quality</label
          ><select id="max-height" v-model="maxHeight">
            <option :value="1080">Best up to 1080p</option>
            <option :value="720">Up to 720p</option>
            <option :value="480">Up to 480p</option>
          </select>
        </div>
        <div>
          <label for="container">Preferred container</label
          ><select id="container" v-model="container">
            <option value="mp4">MP4</option>
            <option value="mkv">MKV</option>
            <option value="webm">WebM</option>
          </select>
        </div>
      </div>
      <label class="checkbox-label"><input v-model="audio" type="checkbox" />Include audio</label>
      <label for="storage-target">Storage destination</label>
      <select id="storage-target" v-model="target">
        <option value="local">Local</option>
        <option value="google_drive" :disabled="!storage.driveReady">
          Google Drive{{ storage.driveReady ? '' : ' (unavailable)' }}
        </option>
      </select>
      <p v-if="!targetReady" class="muted">
        Loading or unavailable destination. <RouterLink to="/storage">Manage Storage</RouterLink>
      </p>
      <p v-if="storage.error" role="alert" class="error">
        {{ storage.error }}
        <button type="button" @click="storage.load">Retry storage status</button>
      </p>
      <label class="checkbox-label"
        ><input v-model="force" type="checkbox" />Force redownload</label
      >
      <p class="muted small">
        Force downloads again even when successful history exists; existing files are kept.
      </p>
      <p class="muted small">
        Quality depends on the source and your backend limit. Video-only output requires a
        video-only source format.
      </p>
      <p v-if="downloads.error" role="alert" class="error-panel">{{ downloads.error }}</p>
      <div class="form-actions">
        <button type="submit" :disabled="downloads.submitting || !targetReady">
          {{ downloads.submitting ? 'Submitting…' : 'Queue downloads' }}</button
        ><button
          type="button"
          class="button-secondary"
          :disabled="urls.length !== 1 || downloads.previewLoading"
          @click="preview"
        >
          {{ downloads.previewLoading ? 'Resolving…' : 'Preview video' }}
        </button>
      </div>
      <p v-if="urls.length > 1" class="muted small">
        Multiple links can be queued directly; preview is available for one video at a time.
      </p>
      <div v-if="downloads.createdIds.length" role="status" class="success-panel">
        {{ downloads.createdIds.length }} job{{
          downloads.createdIds.length === 1 ? '' : 's'
        }}
        created. <RouterLink to="/queue">View Queue →</RouterLink>
      </div>
    </form>
    <aside class="download-aside">
      <section class="panel">
        <h3>Video preview</h3>
        <p v-if="downloads.previewLoading" role="status">Resolving metadata…</p>
        <p v-else-if="downloads.previewError" role="alert" class="error">
          {{ downloads.previewError }}
        </p>
        <template v-else-if="downloads.preview"
          ><img
            v-if="thumbnail"
            :src="thumbnail"
            alt="Video thumbnail"
            loading="lazy"
            referrerpolicy="no-referrer"
            @error="imageFailed = true"
          />
          <div v-else class="thumbnail-fallback">No thumbnail available</div>
          <span class="badge">{{ downloads.preview.platform }}</span>
          <h3 class="preview-title">{{ downloads.preview.title || 'Untitled video' }}</h3>
          <p>{{ downloads.preview.creator || 'Creator unavailable' }}</p>
          <p v-if="downloads.preview.has_download_history !== undefined" class="muted small">
            Successful history: {{ downloads.preview.has_download_history ? 'Yes' : 'No' }} · Stored
            file: {{ downloads.preview.has_file ? 'Yes' : 'No' }}
          </p>
          <p class="muted small">
            {{
              downloads.preview.duration_seconds === null
                ? 'Duration unknown'
                : `${Math.round(downloads.preview.duration_seconds * 10) / 10} seconds`
            }}<span v-if="downloads.preview.height"> · Source {{ downloads.preview.height }}p</span>
          </p>
        </template>
        <p v-else class="muted">
          Paste one video URL and choose Preview video. Preview is optional and does not download
          media.
        </p>
      </section>
      <section class="note-panel">
        <h3>Your local workspace</h3>
        <p>
          Completed downloads appear in Library with their selected storage destination. Successful
          history prevents normal duplicate downloads.
        </p>
        <p>Use public content or content you are authorized to store.</p>
      </section>
    </aside>
  </div>
</template>
