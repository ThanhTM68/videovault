import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, it, vi } from 'vitest'
import App from '../src/App.vue'
import HomeView from '../src/views/HomeView.vue'

it('renders the application shell and backend health through the router', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }))))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: HomeView }],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
  await flushPromises()
  expect(wrapper.find('h1').text()).toBe('VideoVault')
  expect(wrapper.find('[role="status"]').text()).toBe('Backend reachable')
  wrapper.unmount()
})
