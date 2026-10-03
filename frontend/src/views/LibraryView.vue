<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useLibraryStore } from '../stores/library'
import { PLATFORMS, type Platform } from '../types/library'
import { safeImageUrl } from '../utils/download'
import VideoDetails from '../components/VideoDetails.vue'
const library = useLibraryStore()
const search = ref(''),
  platform = ref<Platform | ''>(''),
  file = ref(''),
  history = ref(''),
  tag = ref(''),
  collection = ref('')
const failedImages = ref<Record<string, boolean>>({})
function apply(): void {
  library.filters = {
    search: search.value.trim(),
    platform: platform.value || undefined,
    has_file: file.value ? file.value === 'yes' : undefined,
    has_download_history: history.value ? history.value === 'yes' : undefined,
    tag_id: tag.value || undefined,
    collection_id: collection.value || undefined,
  }
  void library.load(1)
}
onMounted(() => {
  library.filters = {}
  library.selected = null
  void library.load(1)
  void library.organizations()
})
onUnmounted(() => {
  library.stop()
})
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">Local media</p>
      <h2>Library</h2>
      <p class="muted">
        Video metadata, download history and physical files have separate lifecycles.
      </p>
    </div>
    <RouterLink class="button-link" to="/download">Add videos</RouterLink>
  </div>
  <form class="panel library-filters" @submit.prevent="apply">
    <div>
      <label for="library-search">Title or creator</label
      ><input id="library-search" v-model="search" maxlength="255" />
    </div>
    <div>
      <label for="library-platform">Platform</label
      ><select id="library-platform" v-model="platform">
        <option value="">All platforms</option>
        <option v-for="value in PLATFORMS" :key="value" :value="value">{{ value }}</option>
      </select>
    </div>
    <div>
      <label for="file-filter">File state</label
      ><select id="file-filter" v-model="file">
        <option value="">Any file state</option>
        <option value="yes">Has file</option>
        <option value="no">No file</option>
      </select>
    </div>
    <div>
      <label for="history-filter">Successful history</label
      ><select id="history-filter" v-model="history">
        <option value="">Any history state</option>
        <option value="yes">Has successful history</option>
        <option value="no">No successful history</option>
      </select>
    </div>
    <div>
      <label for="library-tag">Tag</label
      ><select id="library-tag" v-model="tag">
        <option value="">All tags</option>
        <option v-for="item in library.tags" :key="item.id" :value="item.id">
          {{ item.name }}
        </option>
      </select>
    </div>
    <div>
      <label for="library-collection">Collection</label
      ><select id="library-collection" v-model="collection">
        <option value="">All collections</option>
        <option v-for="item in library.collections" :key="item.id" :value="item.id">
          {{ item.name }}
        </option>
      </select>
    </div>
    <button :disabled="library.loading">Search</button
    ><button
      type="button"
      class="button-secondary"
      :disabled="library.loading"
      @click="library.load()"
    >
      Refresh
    </button>
  </form>
  <p v-if="library.error" role="alert" class="error-panel">
    {{ library.error }} Previously loaded videos are kept.
  </p>
  <p v-if="library.actionError" role="alert" class="error-panel">{{ library.actionError }}</p>
  <VideoDetails />
  <p v-if="library.loading && !library.items.length" role="status">Loading Library…</p>
  <p v-else-if="!library.items.length && !library.error" class="panel empty-state">
    No videos match this view. Download a video to add it to your library.
  </p>
  <div class="library-grid">
    <article v-for="video in library.items" :key="video.id" class="panel library-card">
      <img
        v-if="safeImageUrl(video.thumbnail_url) && !failedImages[video.id]"
        :src="safeImageUrl(video.thumbnail_url)!"
        alt="Video thumbnail"
        loading="lazy"
        referrerpolicy="no-referrer"
        @error="failedImages[video.id] = true"
      />
      <div v-else class="thumbnail-fallback">No thumbnail available</div>
      <span class="badge">{{ video.platform }}</span>
      <h3>{{ video.title || 'Untitled video' }}</h3>
      <p>{{ video.creator || 'Creator unavailable' }}</p>
      <p class="muted small">
        {{
          video.duration_seconds === null ? 'Duration unknown' : `${video.duration_seconds} seconds`
        }}
        · {{ video.width || '?' }} × {{ video.height || '?' }}
      </p>
      <p>
        History: {{ video.has_download_history ? 'Successful' : 'No successful history'
        }}<br />File: {{ video.has_file ? 'Present' : 'No file' }}
      </p>
      <p class="muted small">
        {{ video.tags.map((item) => item.name).join(' · ') || 'No personal tags' }}
      </p>
      <p class="muted small">
        {{ video.collections.map((item) => item.name).join(' · ') || 'No collections' }}
      </p>
      <button class="button-secondary" :disabled="library.busy" @click="library.select(video.id)">
        View details
      </button>
    </article>
  </div>
  <nav class="pagination" aria-label="Library pages">
    <button
      :disabled="library.page <= 1 || library.loading"
      @click="library.load(library.page - 1)"
    >
      Previous</button
    ><span
      >Page {{ library.page }} of {{ Math.max(1, Math.ceil(library.total / 25)) }} ·
      {{ library.total }} videos</span
    ><button
      :disabled="library.page * 25 >= library.total || library.loading"
      @click="library.load(library.page + 1)"
    >
      Next
    </button>
  </nav>
</template>
