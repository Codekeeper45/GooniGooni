import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import modelManagerPlugin from './vite-plugin-model-manager'

export default defineConfig(({ mode }) => ({
  plugins: [
    // The React and Tailwind plugins are both required for Make, even if
    // Tailwind is not being actively used – do not remove them
    react(),
    tailwindcss(),
    // Model Manager API — dev-only local endpoints for managing ComfyUI models
    ...(mode === 'development' ? [modelManagerPlugin()] : []),
  ],
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
    },
  },

  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],

  // Dev server proxy (local mode only)
  server: mode === 'development' ? {
    proxy: {
      // Admin API — local Python backend (admin_local.py on port 8001)
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (p: string) => p.replace(/^\/api/, ''),
        // Don't fail if local backend is not running
        configure: (proxy) => {
          proxy.on('error', () => {
            // Silently ignore — backend may not be running
          })
        },
      },
      // ComfyUI local inference
      '/comfy-api': {
        target: 'http://127.0.0.1:8188',
        changeOrigin: true,
        rewrite: (p: string) => p.replace(/^\/comfy-api/, ''),
        // Don't fail if ComfyUI is not running
        configure: (proxy) => {
          proxy.on('error', () => {
            // Silently ignore proxy errors — ComfyUI may not be running
          })
        },
      },
    },
  } : undefined,
}))
