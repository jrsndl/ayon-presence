import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default ({ mode }) => {
  Object.assign(process.env, loadEnv(mode, process.cwd(), ''))
  return defineConfig({
    plugins: [react()],
    base: '',
    server: { proxy: { '/api': { target: process.env.SERVER_URL || 'http://localhost:5000', changeOrigin: true } } },
  })
}
