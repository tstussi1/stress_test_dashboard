import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// VITE_BASE_PATH is the only deployment-specific setting: '/<repository>/' on GitHub Pages.
// The default './' makes the built folder work from any location (also straight from disk).
export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? './',
  plugins: [svelte()],
  // 700 KB raw (about 220 KB gzip) is the size of the tree-shaken ECharts core; the enforced limit is the gzip
  // budget in package.json (scripts/check-budgets.mjs).
  build: { target: 'es2022', sourcemap: true, chunkSizeWarningLimit: 700 },
  test: { environment: 'node', include: ['tests/**/*.test.ts'] }
});
