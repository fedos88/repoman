import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// In development (`npm run dev`) backend paths are proxied to a locally running backend.
const backend = 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': backend,
      '/repository': backend,
    },
  },
});
