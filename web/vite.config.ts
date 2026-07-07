import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/radar-viz/',
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/radar-viz/api/airspace/ws': {
        target: 'ws://ai-worker:8000',
        ws: true,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/radar-viz\/api/, ''),
      },
      '/radar-viz/api': {
        target: 'http://ai-worker:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/radar-viz\/api/, ''),
      },
      '/api': {
        target: 'http://ai-worker:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
