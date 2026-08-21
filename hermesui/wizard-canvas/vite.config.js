import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: './',
  plugins: [react()],
  publicDir: '.build-public',
  build: {
    outDir: '../../static/wizard-canvas',
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2022',
    rollupOptions: {
      output: {
        entryFileNames: 'assets/app.min.js',
        chunkFileNames: 'assets/chunk-[name]-[hash].min.js',
        assetFileNames: assetInfo => assetInfo.names?.some(name => name.endsWith('.css'))
          ? 'assets/app.css'
          : 'assets/[name]-[hash][extname]',
      },
    },
  },
});
