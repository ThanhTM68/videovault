import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useHealthStore } from '../src/stores/health'

describe('backend health', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('reports a reachable backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' })))
    vi.stubGlobal('fetch', fetchMock)
    const health = useHealthStore()
    await health.check()
    expect(health.status).toBe('reachable')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', { signal: expect.any(AbortSignal) })
  })

  it.each([
    new Response('unavailable', { status: 503 }),
    new Response(JSON.stringify({ status: 'unexpected' })),
    new Response('invalid json'),
  ])('reports failed or malformed responses as unreachable', async (response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    const health = useHealthStore()
    await health.check()
    expect(health.status).toBe('unreachable')
  })

  it('recovers from a network failure on retry', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }))))
    const health = useHealthStore()
    await health.check()
    expect(health.status).toBe('unreachable')
    await health.check()
    expect(health.status).toBe('reachable')
  })

  it('does not send overlapping checks', async () => {
    let resolveRequest!: (response: Response) => void
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { resolveRequest = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    const health = useHealthStore()
    const pending = health.check()
    expect(health.status).toBe('checking')
    await health.check()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    resolveRequest(new Response(JSON.stringify({ status: 'ok' })))
    await pending
    expect(health.status).toBe('reachable')
  })
})
