import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const html = readFileSync(path.resolve('website/EVHInstinctPDFRAG/index.html'), 'utf8');

test('client search updates for the latest query and ignores stale responses', async ({ page }) => {
  const requests = [];

  await page.route('**/*', async route => {
    const url = route.request().url();
    if (url.endsWith('/api/version')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ version: 'test-sha', lambda_version: '$LATEST' }),
      });
      return;
    }
    if (url.includes('/api/options')) {
      const query = new URL(url).searchParams.get('q') || '';
      requests.push(query);
      const delays = { Bur: 450, Burc: 75, Burch: 50, Burchill: 25 };
      const bodyFor = q => {
        if (q === 'Bur') return { items: [{ label: 'Bur Old', secondary: 'old' }] };
        if (q === 'Burc') return { items: [{ label: 'Burc Interim', secondary: 'mid' }] };
        if (q === 'Burch') return { items: [{ label: 'Burch Interim', secondary: 'mid' }] };
        if (q === 'Burchill') {
          return {
            items: [
              { label: 'Deborah Burchill', secondary: '8762' },
              { label: 'Deborah Burch', secondary: '3234' },
            ],
          };
        }
        return { items: [] };
      };
      await page.waitForTimeout(delays[query] ?? 0);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(bodyFor(query)),
      });
      return;
    }
    if (url === 'https://example.test/' || url === 'http://example.test/' || url.endsWith('/')) {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: html,
      });
      return;
    }
    await route.fulfill({ status: 404, body: '' });
  });

  await page.goto('https://example.test/');
  await expect(page.locator('#live-status')).toHaveText('Ready');

  const client = page.locator('#client-input');
  const menu = page.locator('#client-menu');
  const status = page.locator('#client-status');

  await client.fill('Bur');
  await expect.poll(() => requests.slice()).toContain('Bur');
  await expect(status).toContainText('matches');

  await client.fill('Burchill');
  await expect.poll(() => requests.slice()).toContain('Burchill');
  await expect(menu).toContainText('Deborah Burchill');
  await expect(menu).not.toContainText('Bur Old');

  await page.locator('#client-input').blur();
  await page.locator('#client-input').focus();
  await expect.poll(() => requests.filter(q => q === 'Burchill').length).toBe(1);
  await expect(menu).toContainText('Deborah Burchill');

  await client.fill('Bu');
  await expect(menu).toBeHidden();
  await expect(status).toHaveText('');
});
