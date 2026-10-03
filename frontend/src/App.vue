<script setup lang="ts">
import HomeView from './views/HomeView.vue'
</script>

<template>
  <a class="skip-link" href="#page-content">Skip to content</a>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">V</span>
        <div>
          <h1>VideoVault</h1>
          <p>Local video workspace</p>
        </div>
      </div>
      <nav aria-label="Main navigation">
        <RouterLink to="/" exact-active-class="nav-active"
          ><span aria-hidden="true">▦</span>Dashboard</RouterLink
        ><RouterLink to="/download" active-class="nav-active"
          ><span aria-hidden="true">↓</span>Quick Download</RouterLink
        ><RouterLink to="/queue" active-class="nav-active"
          ><span aria-hidden="true">≡</span>Queue</RouterLink
        >
        <RouterLink to="/library" active-class="nav-active">Library</RouterLink>
        <RouterLink to="/history" active-class="nav-active">History</RouterLink>
        <RouterLink to="/storage" active-class="nav-active">Storage</RouterLink>
        <p class="nav-label">Coming later</p>
        <span
          v-for="name in ['Editor', 'Settings']"
          :key="name"
          class="nav-disabled"
          aria-disabled="true"
          >{{ name }}</span
        >
      </nav>
      <p class="sidebar-note">Your content. Your workspace.</p>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <span class="workspace-label">LOCAL WORKSPACE</span><HomeView />
      </header>
      <main id="page-content" tabindex="-1"><RouterView /></main>
      <footer>VideoVault · Local-first downloads</footer>
    </div>
  </div>
</template>
