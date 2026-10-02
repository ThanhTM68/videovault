export const MAX_URLS = 100
export function parseUrls(text: string): string[] {
  return [
    ...new Set(
      text
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean),
    ),
  ]
}
export function validateUrls(urls: string[]): string | null {
  if (!urls.length) return 'Paste at least one video URL.'
  if (urls.length > MAX_URLS) return `Submit up to ${MAX_URLS} URLs at a time.`
  for (const [index, value] of urls.entries()) {
    try {
      const url = new URL(value)
      if (!['http:', 'https:'].includes(url.protocol) || !url.hostname) throw new Error()
    } catch {
      return `URL ${index + 1} must be a complete HTTP or HTTPS URL.`
    }
  }
  return null
}
export function safeImageUrl(value: string | null): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
      ? url.href
      : null
  } catch {
    return null
  }
}
