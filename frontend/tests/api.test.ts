import { describe, expect, it, vi } from 'vitest'
import { ApiError, isRecord, request } from '../src/api/client'
import { fetchJobs } from '../src/api/jobs'
import { submitDownloads } from '../src/api/downloads'
import { job, jobPage } from './fixtures'

const valid = (data: unknown): data is { ok: boolean } =>
  isRecord(data) && typeof data.ok === 'boolean'
describe('typed API boundary', () => {
  it('sends relative JSON requests and validates successful responses', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })))
    vi.stubGlobal('fetch', fetch)
    expect(await request('/example', valid, { method: 'POST', body: { name: 'value' } })).toEqual({
      ok: true,
    })
    expect(fetch).toHaveBeenCalledWith('/api/v1/example', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"name":"value"}',
      signal: expect.any(AbortSignal),
    })
  })
  it('preserves safe API code/message without displaying validation inputs', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              error: {
                code: 'VALIDATION_ERROR',
                message: 'Request validation failed',
                details: { input: 'secret' },
              },
            }),
            { status: 422 },
          ),
        ),
    )
    await expect(request('/example', valid)).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      status: 422,
      message: 'Request validation failed',
    })
  })
  it.each(['invalid json', JSON.stringify({ wrong: true })])(
    'rejects malformed successful responses',
    async (body) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)))
      await expect(request('/example', valid)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    },
  )
  it('normalizes unavailable backend and non-JSON HTTP errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>secret traceback</html>', { status: 502 })),
    )
    await expect(request('/example', valid)).rejects.toMatchObject({
      code: 'HTTP_ERROR',
      status: 502,
      message: 'VideoVault backend is unavailable. Please try again.',
    })
  })
  it('normalizes network errors without raw diagnostics', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('secret socket traceback')))
    await expect(request('/example', valid)).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      message: 'Cannot connect to the VideoVault backend. Start it and try again.',
    })
  })
  it('identifies deliberate cancellation', async () => {
    const controller = new AbortController()
    controller.abort()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))
    await expect(request('/example', valid, { signal: controller.signal })).rejects.toMatchObject({
      code: 'ABORTED',
    })
  })
  it('validates job responses and query parameters', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(jobPage([job()]))))
    vi.stubGlobal('fetch', fetch)
    await fetchJobs({ status: 'queued', page_size: 25 })
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/jobs?status=queued&page_size=25')
    fetch.mockResolvedValue(
      new Response(
        JSON.stringify(jobPage([job({ status: 'queued' })])).replace('queued', 'invented'),
      ),
    )
    await expect(fetchJobs()).rejects.toBeInstanceOf(ApiError)
  })
  it('does not accept a false successful submission response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ jobs: [] }))))
    await expect(
      submitDownloads({
        urls: ['https://example.com/video'],
        max_height: 1080,
        preferred_container: 'mp4',
        audio_enabled: true,
      }),
    ).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
})
