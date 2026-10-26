import { defineConfig } from '@playwright/test';

// End-to-end tests run against the production build served by `vite preview` (run `npm run build` first,
// or use `npm run e2e`, which does). Set E2E_PORT if 4173 is taken by another server.
const port = process.env.E2E_PORT ?? '4173';

export default defineConfig({
  testDir: 'e2e',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${port}`,
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true
  },
  webServer: {
    command: `npx vite preview --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: true,
    timeout: 60_000
  }
});
