import { isRecord, nullableString, request } from './client'
import type { StorageStatus } from '../types/storage'

export const isStorage = (data: unknown): data is StorageStatus =>
  isRecord(data) &&
  ['local', 'google_drive'].includes(String(data.default_target)) &&
  Array.isArray(data.providers) &&
  data.providers.length === 2 &&
  new Set(data.providers.map((item) => (isRecord(item) ? item.provider : null))).size === 2 &&
  data.providers.every(
    (item) =>
      isRecord(item) &&
      ['local', 'google_drive'].includes(String(item.provider)) &&
      ['configured', 'connected', 'available'].every((key) => typeof item[key] === 'boolean') &&
      ['display_name', 'account_id', 'root_folder_id', 'error_code'].every((key) =>
        nullableString(item[key]),
      ),
  )
export const fetchStorage = (signal?: AbortSignal): Promise<StorageStatus> =>
  request('/storage', isStorage, { signal })
export const disconnectDrive = (): Promise<StorageStatus> =>
  request('/storage/google-drive/disconnect', isStorage, {
    method: 'POST',
    body: {},
    timeout: 120000,
  })
export const connectDrive = (): Promise<{ authorization_url: string }> =>
  request(
    '/storage/google-drive/connect',
    (value): value is { authorization_url: string } => {
      if (!isRecord(value) || typeof value.authorization_url !== 'string') return false
      try {
        const url = new URL(value.authorization_url)
        return (
          url.protocol === 'https:' &&
          url.hostname === 'accounts.google.com' &&
          !url.username &&
          !url.password
        )
      } catch {
        return false
      }
    },
    { method: 'POST', body: {} },
  )
export const setDriveRoot = (folderId?: string): Promise<{ id: string; name: string }> =>
  request(
    '/storage/google-drive/root',
    (value): value is { id: string; name: string } =>
      isRecord(value) && typeof value.id === 'string' && typeof value.name === 'string',
    {
      method: folderId ? 'PUT' : 'POST',
      body: folderId ? { folder_id: folderId } : {},
      timeout: 120000,
    },
  )
