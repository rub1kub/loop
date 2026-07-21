import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    target: 'es2022',
    sourcemap: process.env.LOOP_BUILD_SOURCEMAPS === 'true',
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'tonconnect-ui', test: /node_modules\/@tonconnect\/ui/ },
            { name: 'tonconnect-sdk', test: /node_modules\/@tonconnect\/(sdk|protocol)/ },
            { name: 'ton-core', test: /node_modules\/@ton\// },
            { name: 'motion', test: /node_modules\/motion/ },
            { name: 'react', test: /node_modules\/react(?:-dom)?/ },
          ],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    include: ['src/**/*.test.{ts,tsx}'],
    css: true,
  },
});
