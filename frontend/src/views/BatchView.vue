<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import BatchCandidateCard from '../components/BatchCandidateCard.vue'
import { useBatchStore } from '../stores/batch'
import { useStorageStore } from '../stores/storage'
import type { SourceOrdering, SourceRequest } from '../types/sources'
import type { StorageProvider } from '../types/storage'
import { validateUrls } from '../utils/download'
const batch = useBatchStore(),
  storage = useStorageStore()
const url = ref(''),
  n = ref<string | number>('20'),
  ordering = ref<SourceOrdering>('source')
const minDuration = ref(''),
  maxDuration = ref(''),
  minViews = ref(''),
  maxViews = ref('')
const dateFrom = ref(''),
  dateTo = ref('')
const height = ref<1080 | 720 | 480>(1080),
  container = ref<'mp4' | 'mkv' | 'webm'>('mp4')
const audio = ref(true),
  force = ref(false),
  target = ref<StorageProvider>('local')
const validation = ref<string | null>(null)
const caps = computed(() => batch.capabilities)
const targetReady = computed(
  () =>
    !!storage.status &&
    !storage.error &&
    !storage.loading &&
    !!storage.status.providers.find((item) => item.provider === target.value)?.available,
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
watch(url, () => {
  batch.invalidate(true)
  ordering.value = 'source'
  minDuration.value = maxDuration.value = minViews.value = maxViews.value = ''
  dateFrom.value = dateTo.value = ''
  validation.value = null
})
watch([n, ordering, minDuration, maxDuration, minViews, maxViews, dateFrom, dateTo], () => {
  batch.invalidate()
  validation.value = null
})
watch(force, (value) => batch.syncForce(value))
onMounted(() => {
  void storage.load()
})
onUnmounted(() => batch.invalidate(true))
async function preview(): Promise<void> {
  validation.value = validateUrls([url.value.trim()])
  if (url.value.trim().length > 2048) validation.value = 'Source URL is too long.'
  const limit = Number(n.value)
  if (!String(n.value).trim() || !Number.isInteger(limit) || limit < 1 || limit > 100)
    validation.value = 'N must be an integer from 1 to 100.'
  const criteria: SourceRequest = { url: url.value.trim(), n: limit, ordering: ordering.value }
  for (const [lowKey, highKey, lowValue, highValue, integer] of [
    ['min_duration', 'max_duration', minDuration.value, maxDuration.value, false],
    ['min_views', 'max_views', minViews.value, maxViews.value, true],
  ] as const) {
    for (const [key, value] of [
      [lowKey, lowValue],
      [highKey, highValue],
    ] as const) {
      if (value === '') continue
      const number = Number(value)
      if (!Number.isFinite(number) || number < 0 || (integer && !Number.isInteger(number)))
        validation.value = 'Filters must be nonnegative numbers; views must be integers.'
      criteria[key] = number
    }
    if (
      criteria[lowKey] !== undefined &&
      criteria[highKey] !== undefined &&
      criteria[lowKey]! > criteria[highKey]!
    )
      validation.value = 'Minimum must not exceed maximum.'
  }
  if (dateFrom.value) criteria.date_from = dateFrom.value
  if (dateTo.value) criteria.date_to = dateTo.value
  if (dateFrom.value && dateTo.value && dateFrom.value > dateTo.value)
    validation.value = 'Start date must not follow end date.'
  if (!validation.value) await batch.load(criteria)
}
async function submit(): Promise<void> {
  if (!targetReady.value) return
  await batch.submit({
    max_height: height.value,
    preferred_container: container.value,
    audio_enabled: audio.value,
    storage_target: target.value,
    force: force.value,
  })
}
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">Channel research</p>
      <h2>Batch Download</h2>
      <p class="muted">Preview a public source, select videos, then add ordinary jobs to Queue.</p>
    </div>
  </div>
  <div class="download-layout">
    <form class="panel batch-form" @submit.prevent="preview">
      <fieldset :disabled="batch.submitting">
        <label for="source-url">Channel / profile URL</label>
        <input
          id="source-url"
          v-model="url"
          type="url"
          maxlength="2048"
          placeholder="https://www.youtube.com/@channel/videos"
        />
        <p class="muted small">
          YouTube @handle and /channel/UC… with optional /videos. Other platforms do not support
          source listing yet.
        </p>
        <div class="options-grid">
          <div>
            <label for="batch-n">Maximum candidates (N)</label
            ><input id="batch-n" v-model="n" type="number" min="1" max="100" step="1" />
          </div>
          <div>
            <label for="source-order">Ordering</label
            ><select id="source-order" v-model="ordering">
              <option value="source">Source order</option>
              <option value="newest" :disabled="!caps?.sort_newest">Newest</option>
              <option value="oldest" :disabled="!caps?.sort_oldest">Oldest</option>
              <option value="views" :disabled="!caps?.sort_views">Most views</option>
            </select>
          </div>
        </div>
        <p class="muted small">
          Source order is the order returned by the source, without a newest/oldest guarantee. We
          inspect at most 100 entries; this is not a whole-channel ranking.
        </p>
        <div class="options-grid">
          <div>
            <label for="duration-min">Minimum duration (seconds)</label
            ><input
              id="duration-min"
              v-model="minDuration"
              type="number"
              min="0"
              step="any"
              :disabled="!caps?.filter_duration"
            />
          </div>
          <div>
            <label for="duration-max">Maximum duration (seconds)</label
            ><input
              id="duration-max"
              v-model="maxDuration"
              type="number"
              min="0"
              step="any"
              :disabled="!caps?.filter_duration"
            />
          </div>
          <div>
            <label for="views-min">Minimum views</label
            ><input
              id="views-min"
              v-model="minViews"
              type="number"
              min="0"
              step="1"
              :disabled="!caps?.filter_views"
            />
          </div>
          <div>
            <label for="views-max">Maximum views</label
            ><input
              id="views-max"
              v-model="maxViews"
              type="number"
              min="0"
              step="1"
              :disabled="!caps?.filter_views"
            />
          </div>
          <div>
            <label for="date-from">Date from</label
            ><input id="date-from" v-model="dateFrom" type="date" :disabled="!caps?.filter_date" />
          </div>
          <div>
            <label for="date-to">Date to</label
            ><input id="date-to" v-model="dateTo" type="date" :disabled="!caps?.filter_date" />
          </div>
        </div>
        <p class="muted small">
          Preview once to discover capabilities. Disabled filters are unsupported. Ranges are
          inclusive; unknown duration is excluded only when a duration filter is requested.
        </p>
        <p v-if="validation" class="error" role="alert">{{ validation }}</p>
        <button type="submit" :disabled="batch.loading">
          {{ batch.loading ? 'Loading preview…' : 'Preview source' }}
        </button>
      </fieldset>
    </form>
    <section class="panel batch-form">
      <h3>Download options</h3>
      <fieldset :disabled="batch.submitting">
        <div class="options-grid">
          <div>
            <label for="batch-height">Maximum quality</label
            ><select id="batch-height" v-model="height">
              <option :value="1080">Up to 1080p</option>
              <option :value="720">Up to 720p</option>
              <option :value="480">Up to 480p</option>
            </select>
          </div>
          <div>
            <label for="batch-container">Preferred container</label
            ><select id="batch-container" v-model="container">
              <option>mp4</option>
              <option>mkv</option>
              <option>webm</option>
            </select>
          </div>
        </div>
        <label class="checkbox-label"
          ><input id="batch-audio" v-model="audio" type="checkbox" />Include audio</label
        >
        <label for="batch-target">Storage destination</label
        ><select id="batch-target" v-model="target">
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
          ><input id="batch-force" v-model="force" type="checkbox" />Force redownload</label
        >
        <p class="muted small">
          Successful history disables normal selection. Force allows it and keeps previous files;
          repeated selections still create one job per video.
        </p>
        <p class="muted small">
          Changing download options keeps the preview. Changing source, N, ordering or filters
          requires a fresh preview.
        </p>
      </fieldset>
    </section>
  </div>
  <p v-if="batch.loading" role="status">Loading source metadata…</p>
  <p v-if="batch.error" class="error-panel" role="alert">
    {{ batch.error }} Check <RouterLink to="/queue">Queue</RouterLink> after a submission connection
    failure before previewing again.
  </p>
  <section v-if="batch.result" class="success-panel" role="status">
    {{ batch.result.created_count }} jobs queued · {{ batch.result.skipped_history_count }} skipped
    by history · {{ batch.result.skipped_duplicate_selection_count }} duplicate selections skipped.
    <RouterLink to="/queue">View Queue →</RouterLink>
    <p v-for="(item, index) in batch.result.outcomes" :key="index" class="small">
      {{ item.platform_video_id }}: {{ item.outcome }}
    </p>
  </section>
  <section v-if="batch.preview" class="batch-preview">
    <h3>{{ batch.preview.source.display_name ?? 'Source preview' }}</h3>
    <p class="muted">
      {{ batch.preview.statistics.returned_count }} candidates ·
      {{ batch.preview.statistics.enumerated_count }} entries inspected ·
      {{ batch.preview.statistics.already_downloaded_count }} with successful history
    </p>
    <p class="muted small">
      {{ batch.preview.statistics.rejected_count }} rejected ·
      {{ batch.preview.statistics.duplicate_count }} repeated identities ·
      {{ batch.preview.statistics.filtered_count }} outside duration range ·
      {{ batch.preview.statistics.metadata_unavailable_count }} missing requested metadata. Channel
      total unavailable. Preview expires after 10 minutes or a backend restart.
    </p>
    <p v-if="!batch.preview.candidates.length">No candidates match this bounded preview.</p>
    <div class="form-actions">
      <button
        type="button"
        class="button-secondary"
        :disabled="!batch.valid || batch.submitting"
        @click="batch.selectAll(force)"
      >
        Select all eligible
      </button>
      <button
        type="button"
        class="button-secondary"
        :disabled="batch.submitting"
        @click="batch.clear"
      >
        Clear selection
      </button>
      <span>{{ batch.selectedIds.length }} selected</span>
      <button
        id="batch-submit"
        type="button"
        :disabled="!batch.valid || !batch.selectedIds.length || batch.submitting || !targetReady"
        @click="submit"
      >
        {{ batch.submitting ? 'Submitting…' : 'Queue selected' }}
      </button>
    </div>
    <p v-if="!batch.valid" class="muted">Preview again before another submission.</p>
    <div class="library-grid">
      <BatchCandidateCard
        v-for="candidate in batch.preview.candidates"
        :key="candidate.platform_video_id"
        :candidate="candidate"
        :selected="batch.selectedIds.includes(candidate.platform_video_id)"
        :disabled="batch.submitting || !batch.eligible(candidate.platform_video_id, force)"
        @select="batch.select(candidate.platform_video_id, $event, force)"
      />
    </div>
  </section>
</template>
