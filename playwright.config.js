import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/playwright',
  use: {
    headless: true,
    launchOptions: {
      executablePath: process.env.PW_CHROMIUM_PATH || '/home/ggb66/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome',
    },
  },
});
