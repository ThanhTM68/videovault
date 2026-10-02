import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

const repositoryRoot = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repositoryRoot, '')
  const host = env.APP_HOST || '127.0.0.1'
  const port = env.APP_PORT || '8000'

  return {
    plugins: [vue()],
    envDir: repositoryRoot,
    server: {
      port: 5173,
      strictPort: true,
      proxy: { '/api': { target: `http://${host}:${port}` } },
    },
    test: {
      environment: 'jsdom',
      include: ['tests/**/*.test.ts'],
      restoreMocks: true,
      unstubGlobals: true,
    },
  }
})
