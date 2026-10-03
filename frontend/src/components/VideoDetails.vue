<script setup lang="ts">
import { ref, watch } from 'vue'
import { useLibraryStore } from '../stores/library'
import type { DeleteOperation } from '../types/library'
import { formatDate } from '../utils/jobs'
const library = useLibraryStore()
const confirmation = ref<DeleteOperation | null>(null),
  typedConfirmation = ref('')
const tagName = ref(''),
  collectionName = ref(''),
  tagId = ref(''),
  collectionId = ref('')
const copy = {
  file: 'Delete file: managed media files will be removed. Download history will remain. Normal downloads may still be treated as duplicates.',
  history:
    'Remove history: media files will remain. This video becomes eligible for a normal download again.',
  all: 'Delete everything: managed media files and download history for this video will be removed. Metadata, tags and collections remain.',
}
function ask(operation: DeleteOperation): void {
  confirmation.value = operation
  typedConfirmation.value = ''
}
watch(
  () => library.selected?.id,
  () => {
    confirmation.value = null
    typedConfirmation.value = ''
  },
)
async function confirm(): Promise<void> {
  if (!confirmation.value || (confirmation.value === 'all' && typedConfirmation.value !== 'DELETE'))
    return
  await library.action(confirmation.value)
  if (!library.actionError) confirmation.value = null
}
async function add(kind: 'tags' | 'collections'): Promise<void> {
  const name = kind === 'tags' ? tagName.value.trim() : collectionName.value.trim()
  const id = kind === 'tags' ? tagId.value : collectionId.value
  if (!name && !id) return
  await library.organize(kind, id, false, name || undefined)
  if (!library.actionError) {
    tagName.value = ''
    collectionName.value = ''
  }
}
</script>
<template>
  <section v-if="library.selected" class="panel video-details" aria-label="Video details">
    <div class="section-heading">
      <h3>{{ library.selected.title || 'Untitled video' }}</h3>
      <button class="button-secondary" :disabled="library.busy" @click="library.selected = null">
        Close details
      </button>
    </div>
    <p>{{ library.selected.description || 'No description available.' }}</p>
    <p class="muted">
      Successful history: {{ library.selected.has_download_history ? 'Yes' : 'No' }} · Stored file
      (Drive last-known):
      {{ library.selected.has_file ? 'Yes' : 'No' }}
    </p>
    <div class="form-actions">
      <button :disabled="library.busy" @click="library.action('force')">Force redownload</button>
      <button class="button-secondary" :disabled="library.busy" @click="ask('file')">
        Delete file
      </button>
      <button class="button-secondary" :disabled="library.busy" @click="ask('history')">
        Remove history
      </button>
      <button class="button-secondary" :disabled="library.busy" @click="ask('all')">
        Delete everything
      </button>
    </div>
    <p class="muted small">
      Force downloads again even when successful history exists. Previous files are kept.
    </p>
    <div
      v-if="confirmation"
      role="alertdialog"
      aria-label="Confirm library action"
      class="note-panel"
    >
      <p>{{ copy[confirmation] }}</p>
      <label v-if="confirmation === 'all'" for="confirm-delete"
        >Type DELETE to confirm<input
          id="confirm-delete"
          v-model="typedConfirmation"
          autocomplete="off"
      /></label>
      <div class="form-actions">
        <button
          :disabled="library.busy || (confirmation === 'all' && typedConfirmation !== 'DELETE')"
          @click="confirm"
        >
          Confirm action</button
        ><button class="button-secondary" :disabled="library.busy" @click="confirmation = null">
          Keep current state
        </button>
      </div>
    </div>
    <p v-if="library.notice" role="status" class="success-panel">
      {{ library.notice }} <RouterLink to="/queue">View Queue</RouterLink>
    </p>
    <h3>Managed files</h3>
    <button class="button-secondary" :disabled="library.busy" @click="library.action('refresh')">
      Refresh file availability
    </button>
    <p v-if="!library.selected.files.length" class="muted">No managed media files.</p>
    <div v-for="file in library.selected.files" :key="file.id" class="file-summary">
      <p>
        {{ file.storage_provider === 'google_drive' ? 'Google Drive' : 'Local' }} -
        {{ file.file_name }}
      </p>
      <span class="badge">{{ file.state === 'stored' ? 'Stored (last-known)' : file.state }}</span>
      {{ file.container }} · {{ file.width || '?' }} × {{ file.height || '?' }} ·
      {{ file.size_bytes }} bytes
      <p class="hash">SHA-256: {{ file.sha256 || 'Unavailable' }}</p>
    </div>
    <p class="muted small">
      Missing files keep their history. Local presence is checked on detail. Drive is last-known;
      use Refresh file availability to check it explicitly.
    </p>
    <h3>Download history</h3>
    <p v-if="!library.selected.history.length" class="muted">No download history for this video.</p>
    <p v-for="event in library.selected.history" :key="event.id">
      {{ event.status }} · {{ event.forced ? 'Forced' : 'Normal' }} ·
      {{ formatDate(event.created_at) }}
    </p>
    <div class="options-grid">
      <section>
        <h3>Personal tags</h3>
        <p v-for="tag in library.selected.tags" :key="tag.id">
          {{ tag.name }}
          <button
            class="button-secondary"
            :disabled="library.busy"
            @click="library.organize('tags', tag.id, true)"
          >
            Remove tag
          </button>
        </p>
        <label for="tag-choice">Existing tag</label
        ><select id="tag-choice" v-model="tagId">
          <option value="">Choose a tag</option>
          <option v-for="tag in library.tags" :key="tag.id" :value="tag.id">{{ tag.name }}</option>
        </select>
        <label for="tag-name">New personal tag</label
        ><input id="tag-name" v-model="tagName" maxlength="255" /><button
          :disabled="library.busy || (!tagId && !tagName.trim())"
          @click="add('tags')"
        >
          Add tag
        </button>
      </section>
      <section>
        <h3>Collections</h3>
        <p v-for="item in library.selected.collections" :key="item.id">
          {{ item.name }}
          <button
            class="button-secondary"
            :disabled="library.busy"
            @click="library.organize('collections', item.id, true)"
          >
            Remove collection
          </button>
        </p>
        <label for="collection-choice">Existing collection</label
        ><select id="collection-choice" v-model="collectionId">
          <option value="">Choose a collection</option>
          <option v-for="item in library.collections" :key="item.id" :value="item.id">
            {{ item.name }}
          </option>
        </select>
        <label for="collection-name">New collection</label
        ><input id="collection-name" v-model="collectionName" maxlength="255" /><button
          :disabled="library.busy || (!collectionId && !collectionName.trim())"
          @click="add('collections')"
        >
          Add collection
        </button>
      </section>
    </div>
  </section>
</template>
