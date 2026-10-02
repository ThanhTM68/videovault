import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import DownloadView from '../views/DownloadView.vue'
import QueueView from '../views/QueueView.vue'

export const routes = [
  { path: '/', name: 'dashboard', component: DashboardView },
  { path: '/dashboard', redirect: '/' },
  { path: '/download', name: 'download', component: DownloadView },
  { path: '/queue', name: 'queue', component: QueueView },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
