import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, it, vi } from 'vitest'
import App from '../src/App.vue'
import HomeView from '../src/views/HomeView.vue'
import { routes } from '../src/router'
import { job, jobPage } from './fixtures'
import type { JobStatus } from '../src/types/jobs'

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

it('renders an offline proxy failure and recovers real queue data on refresh', async () => {
  let available = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      if (!available) return new Response('Proxy upstream unavailable', { status: 500 })
      const url = new URL(input, 'http://localhost')
      if (url.pathname.endsWith('/health')) return new Response(JSON.stringify({ status: 'ok' }))
      if (url.pathname.endsWith('/queue')) return new Response(JSON.stringify({ paused: false }))
      return new Response(
        JSON.stringify(
          jobPage([job()], {
            page: Number(url.searchParams.get('page') || 1),
            page_size: Number(url.searchParams.get('page_size') || 25),
            status: (url.searchParams.get('status') || undefined) as JobStatus | undefined,
          }),
        ),
      )
    }),
  )
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/queue')
  const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
  await flushPromises()
  expect(wrapper.text()).toContain('Backend unreachable')
  expect(wrapper.text()).toContain('The server could not complete this request')
  expect(
    wrapper
      .findAll('button')
      .find((button) => button.text() === 'Pause Queue')
      ?.attributes('disabled'),
  ).toBeDefined()
  available = true
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Refresh')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('Backend reachable')
  expect(wrapper.find('article').text()).toContain('Queued')
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  wrapper.unmount()
})
