import { expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '../src/router'
it('resolves core views and redirects unknown paths without fake feature routes', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes })
  for (const [path, name] of [
    ['/', 'dashboard'],
    ['/download', 'download'],
    ['/queue', 'queue'],
    ['/library', 'library'],
    ['/history', 'history'],
  ]) {
    await router.push(path)
    expect(router.currentRoute.value.name).toBe(name)
  }
  await router.push('/dashboard')
  expect(router.currentRoute.value.name).toBe('dashboard')
  await router.push('/unknown-feature')
  expect(router.currentRoute.value.name).toBe('dashboard')
})
