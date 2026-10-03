import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import DownloadView from '../views/DownloadView.vue'
import QueueView from '../views/QueueView.vue'
import LibraryView from '../views/LibraryView.vue'
import HistoryView from '../views/HistoryView.vue'
import StorageView from '../views/StorageView.vue'
import BatchView from '../views/BatchView.vue'

export const routes = [
  { path: '/', name: 'dashboard', component: DashboardView },
  { path: '/dashboard', redirect: '/' },
  { path: '/download', name: 'download', component: DownloadView },
  { path: '/queue', name: 'queue', component: QueueView },
  { path: '/library', name: 'library', component: LibraryView },
  { path: '/history', name: 'history', component: HistoryView },
  { path: '/storage', name: 'storage', component: StorageView },
  { path: '/batch', name: 'batch', component: BatchView },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
