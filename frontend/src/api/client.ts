export const API_BASE = '/api/v1'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
export const nullableString = (value: unknown): value is string | null =>
  value === null || typeof value === 'string'
export const nullableNumber = (value: unknown): value is number | null =>
  value === null || (typeof value === 'number' && Number.isFinite(value))

export function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : 'Unable to complete this request. Please try again.'
}

export async function request<T>(
  path: string,
  validate: (data: unknown) => data is T,
  options: {
    method?: 'POST' | 'PUT' | 'DELETE'
    body?: unknown
    signal?: AbortSignal
    timeout?: number
  } = {},
): Promise<T> {
  const timeout = AbortSignal.timeout(options.timeout ?? 10000)
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout
  try {
    const init: RequestInit = { signal }
    if (options.method) init.method = options.method
    if (options.body !== undefined) {
      init.headers = { 'Content-Type': 'application/json' }
      init.body = JSON.stringify(options.body)
    }
    const response = await fetch(API_BASE + path, init)
    let data: unknown
    try {
      data = await response.json()
    } catch (failure) {
      if (signal.aborted) throw failure
      data = null
    }
    signal.throwIfAborted()
    if (!response.ok) {
      if (
        isRecord(data) &&
        isRecord(data.error) &&
        typeof data.error.code === 'string' &&
        typeof data.error.message === 'string'
      ) {
        throw new ApiError(data.error.message, data.error.code, response.status)
      }
      throw new ApiError(
        response.status === 502 || response.status === 503
          ? 'VideoVault backend is unavailable. Please try again.'
          : 'The server could not complete this request.',
        'HTTP_ERROR',
        response.status,
      )
    }
    if (!validate(data))
      throw new ApiError(
        'The backend returned an unexpected response. Please refresh.',
        'INVALID_RESPONSE',
        response.status,
      )
    return data
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (options.signal?.aborted) throw new ApiError('Request cancelled', 'ABORTED')
    if (timeout.aborted)
      throw new ApiError(
        'Request timed out. Refresh Queue to check the current state.',
        'REQUEST_TIMEOUT',
      )
    throw new ApiError(
      'Cannot connect to the VideoVault backend. Start it and try again.',
      'NETWORK_ERROR',
    )
  }
}
