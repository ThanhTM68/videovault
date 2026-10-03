<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useStorageStore } from '../stores/storage'
const storage = useStorageStore()
const route = useRoute()
const folderId = ref(''),
  disconnectConfirmed = ref(false)
async function disconnect(): Promise<void> {
  await storage.action('disconnect')
  if (!storage.error) disconnectConfirmed.value = false
}
onMounted(() => {
  void storage.load()
})
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">Choose where media lives</p>
      <h2>Storage</h2>
      <p class="muted">Download history stays in VideoVault, independently of stored files.</p>
    </div>
    <button
      class="button-secondary"
      :disabled="storage.loading || storage.busy"
      @click="storage.load"
    >
      Refresh status
    </button>
  </div>
  <p v-if="storage.loading" role="status">Loading storage status…</p>
  <p v-if="storage.error" role="alert" class="error-panel">
    {{ storage.error }} Previously loaded status may be stale.
  </p>
  <p v-if="route.query.drive === 'error'" role="alert" class="error-panel">
    Google connection was not completed. Refresh status and try connecting again.
  </p>
  <section class="panel">
    <h3>Local storage</h3>
    <p>Media is saved under the configured local library folder.</p>
    <p v-if="storage.status">
      Default download destination:
      {{ storage.status.default_target === 'local' ? 'Local' : 'Google Drive' }}
    </p>
  </section>
  <section class="panel">
    <h3>Google Drive</h3>
    <template v-if="storage.drive">
      <p v-if="!storage.drive.configured">
        Not configured. Set the Google OAuth client configuration on the backend to enable Drive.
      </p>
      <template v-else>
        <p>
          {{ storage.drive.connected ? 'Connected' : 'Not connected'
          }}<span v-if="storage.drive.display_name"> · {{ storage.drive.display_name }}</span>
        </p>
        <p v-if="storage.drive.error_code" class="muted">{{ storage.drive.error_code }}</p>
        <button :disabled="storage.busy || storage.loading" @click="storage.action('connect')">
          {{ storage.drive.connected ? 'Reconnect Google Drive' : 'Connect Google Drive' }}
        </button>
        <a v-if="storage.authorizationUrl" :href="storage.authorizationUrl" rel="noreferrer"
          >Continue to Google</a
        >
        <template v-if="storage.drive.connected">
          <p>Root folder: {{ storage.drive.root_folder_id || 'Not selected' }}</p>
          <form @submit.prevent="storage.action('root', folderId.trim())">
            <label for="drive-root">Accessible Drive folder ID</label
            ><input
              id="drive-root"
              v-model="folderId"
              pattern="[A-Za-z0-9_-]{1,256}"
              maxlength="256"
              required
            />
            <div class="form-actions">
              <button :disabled="storage.busy || storage.loading || !folderId.trim()">
                Use folder
              </button>
              <button
                type="button"
                class="button-secondary"
                :disabled="storage.busy || storage.loading"
                @click="storage.action('root')"
              >
                Create / reuse VideoVault folder
              </button>
            </div>
          </form>
          <p class="muted small">
            Access is limited to files this app creates or is explicitly allowed to use. Pasting an
            arbitrary folder ID does not grant access. No Google Picker is included.
          </p>
          <label class="checkbox-label"
            ><input v-model="disconnectConfirmed" type="checkbox" />Disconnect locally; keep all
            media and history</label
          >
          <button
            class="button-secondary"
            :disabled="storage.busy || storage.loading || !disconnectConfirmed"
            @click="disconnect"
          >
            Disconnect Google Drive
          </button>
        </template>
      </template>
    </template>
    <p class="muted small">
      Credentials stay on the backend. Disconnect removes local credentials; revoke consent in your
      Google account separately. Reconnect the same account to manage existing files.
    </p>
  </section>
</template>
