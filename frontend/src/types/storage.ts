export type StorageProvider = 'local' | 'google_drive'
export interface ProviderStatus {
  provider: StorageProvider
  configured: boolean
  connected: boolean
  available: boolean
  display_name: string | null
  account_id: string | null
  root_folder_id: string | null
  error_code: string | null
}
export interface StorageStatus {
  default_target: StorageProvider
  providers: ProviderStatus[]
}
