import { isRecord } from '../api/client'

export function requestedOptions(value: string): string {
  try {
    const options: unknown = JSON.parse(value)
    if (
      !isRecord(options) ||
      typeof options.max_height !== 'number' ||
      !['mp4', 'mkv', 'webm'].includes(String(options.preferred_container)) ||
      typeof options.audio_enabled !== 'boolean'
    )
      return 'Options unavailable'
    return `Up to ${options.max_height}p · ${String(options.preferred_container).toUpperCase()} · ${options.audio_enabled ? 'With audio' : 'Video only'}`
  } catch {
    return value === 'best' ? 'Best available quality' : 'Options unavailable'
  }
}
