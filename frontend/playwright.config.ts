import { defineConfig } from '@playwright/test';

const external = process.env.UI_QA_BASE_URL;
export default defineConfig({
  testDir: './e2e', timeout: 60_000, expect: { timeout: 15_000 }, workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: external ?? 'http://127.0.0.1:18120', headless: true, channel: process.env.UI_QA_CHROME ? 'chrome' : undefined, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: external ? undefined : [
    { command: 'node e2e/fixture-server.mjs', url: 'http://127.0.0.1:18121/api/v1/health', reuseExistingServer: !process.env.CI },
    { command: process.env.CI ? 'node node_modules/next/dist/bin/next start -p 18120' : 'node node_modules/next/dist/bin/next dev --webpack -p 18120', url: 'http://127.0.0.1:18120/dashboard/overview', timeout: 120_000, reuseExistingServer: !process.env.CI, env: { SEO_BRAIN_API_URL: 'http://127.0.0.1:18121', SEO_BRAIN_API_TOKEN: '', NEXT_TELEMETRY_DISABLED: '1' } }
  ]
});
