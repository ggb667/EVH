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

test('source PDF page-count badge keeps 1-2 digit counts fully visible', async ({ page }) => {
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
  const counts = [2, 9, 10, 99];
  for (const count of counts) {
    const chip = await page.evaluateHandle(c => {
      const doc = { document_title: `PDF ${c}`, document_id: `doc-${c}`, pages: Array.from({ length: c }, (_, i) => i + 1) };
      const chip = window.sourceChip(doc, []);
      chip.style.margin = '12px';
      document.body.appendChild(chip);
      return chip;
    }, count);
    const chipLocator = page.locator(`button.source-chip[data-doc-id="doc-${count}"]`);
    const badge = chipLocator.locator('.count');
    await expect(chipLocator).toBeVisible();
    await expect(badge).toBeVisible();
    await expect(badge).toHaveText(String(count));
    const box = await badge.boundingBox();
    expect(box).not.toBeNull();
    expect(box.height).toBeGreaterThanOrEqual(16);
    await expect(badge).toHaveCSS('line-height', '18px');
    await expect(badge).toHaveCSS('bottom', '-4px');
    await chip.dispose();
  }
});

test('patient list is loaded once per client and reused locally after clear', async ({ page }) => {
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
      const kind = new URL(url).searchParams.get('kind') || '';
      const clientId = new URL(url).searchParams.get('clientId') || '';
      requests.push({ kind, query, clientId });
      const bodyFor = () => {
        if (kind === 'client') {
          if (query === '') return { items: [{ id: 'client-1', label: 'Mary Theresa Jeffries', secondary: '8762', pet_count: 2 }] };
          if (query.toLowerCase() === 'mary') return { items: [{ id: 'client-1', label: 'Mary Theresa Jeffries', secondary: '8762', pet_count: 2 }] };
          return { items: [] };
        }
        if (kind === 'pet' && clientId === 'client-1') {
          if (query === '') {
            return {
              items: [
                { id: 'pet-1', label: 'Lassie', secondary: 'Canine · Collie', species: 'Canine', breed: 'Collie' },
                { id: 'pet-2', label: 'Minnie', secondary: 'Canine · Yorkshire Terrier', species: 'Canine', breed: 'Yorkshire Terrier' },
                { id: 'pet-4', label: 'Emmett Bleu (#4)', secondary: 'Canine · Mixed', species: 'Canine', breed: 'Mixed' },
              ],
            };
          }
          if (query.toLowerCase() === 'las' || query.toLowerCase() === 'lassie') {
            return { items: [{ id: 'pet-1', label: 'Lassie', secondary: 'Canine · Collie', species: 'Canine', breed: 'Collie' }] };
          }
          if (query.toLowerCase().includes('emm')) {
            return {
              items: [
                { id: 'pet-4', label: 'Emmett Bleu (#4)', secondary: 'Canine · Mixed', species: 'Canine', breed: 'Mixed' },
                { id: 'pet-2', label: 'Minnie', secondary: 'Canine · Yorkshire Terrier', species: 'Canine', breed: 'Yorkshire Terrier' },
                { id: 'pet-1', label: 'Lassie', secondary: 'Canine · Collie', species: 'Canine', breed: 'Collie' },
              ],
            };
          }
          return {
            items: [
              { id: 'pet-2', label: 'Minnie', secondary: 'Canine · Yorkshire Terrier', species: 'Canine', breed: 'Yorkshire Terrier' },
              { id: 'pet-4', label: 'Emmett Bleu (#4)', secondary: 'Canine · Mixed', species: 'Canine', breed: 'Mixed' },
              { id: 'pet-1', label: 'Lassie', secondary: 'Canine · Collie', species: 'Canine', breed: 'Collie' },
            ],
          };
        }
        return { items: [] };
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(bodyFor()),
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
  const client = page.locator('#client-input');
  const clientMenu = page.locator('#client-menu');
  const pet = page.locator('#pet-input');
  const petMenu = page.locator('#pet-menu');
  const transcript = page.locator('#transcript');

  await client.fill('Mary');
  await expect(clientMenu).toContainText('Mary Theresa Jeffries');
  await page.getByText('Mary Theresa Jeffries').click();
  await expect(client).toHaveValue('Mary Theresa Jeffries');

  await expect(pet).toBeEnabled();
  await expect(pet).toHaveAttribute('placeholder', 'Type a patient name');
  await expect.poll(() => requests.filter(r => r.kind === 'pet').length).toBe(1);
  await expect(petMenu).toContainText('Lassie');
  await expect(petMenu).toContainText('Minnie');

  await pet.focus();
  await expect(petMenu).toContainText('Lassie');
  await expect(petMenu).toContainText('Minnie');

  await pet.fill('La');
  await expect(petMenu).toContainText('Lassie');
  await expect(petMenu).toContainText('Minnie');
  await expect(requests.filter(r => r.kind === 'pet').length).toBe(1);
  await page.getByText('Lassie').click();
  await expect(pet).toHaveValue('Lassie');
  await expect(page.locator('#question-helper')).toContainText('Ask a question to begin a patient-specific conversation.');

  await pet.fill('');
  await expect(petMenu).toContainText('Lassie');
  await expect(petMenu).toContainText('Minnie');
  await expect(petMenu).toContainText('Emmett Bleu (#4)');

  await pet.fill('Emm ABC');
  await expect(petMenu).toContainText('Emmett Bleu (#4)');
  await expect(petMenu).toContainText('Minnie');
  await expect(petMenu).toContainText('Lassie');
  await expect(petMenu.locator('.option').first()).toContainText('Emmett Bleu (#4)');

  await client.fill('');
  await expect(client).toHaveValue('');
  await expect(pet).toBeDisabled();
  await expect(pet).toHaveAttribute('placeholder', 'Select a client first');
  await expect(page.locator('#client-status')).toHaveText('');

  await client.fill('Mary');
  await page.getByText('Mary Theresa Jeffries').click();
  await expect(client).toHaveValue('Mary Theresa Jeffries');
  await expect(pet).toBeEnabled();
  await expect(pet).toHaveAttribute('placeholder', 'Type a patient name');
  await expect(page.locator('#question-helper')).toContainText('Ask a question to begin a patient-specific conversation.');
  await expect.poll(() => requests.filter(r => r.kind === 'pet').length).toBe(2);
  await pet.focus();
  await expect(petMenu).toContainText('Lassie');
  await expect(petMenu).toContainText('Minnie');
  await pet.fill('Min');
  await expect(petMenu).toContainText('Minnie');
  await expect(requests.filter(r => r.kind === 'pet').length).toBe(2);
});

test('clearing client disables patient input and resets prompt', async ({ page }) => {
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
      const kind = new URL(url).searchParams.get('kind') || '';
      const clientId = new URL(url).searchParams.get('clientId') || '';
      const body = kind === 'client'
        ? { items: [{ id: 'client-1', label: 'Mary Theresa Jeffries', secondary: '8762', pet_count: 2 }] }
        : clientId === 'client-1'
          ? { items: [{ id: 'pet-1', label: 'Lassie', secondary: 'Canine · Collie', species: 'Canine', breed: 'Collie' }] }
          : { items: [] };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
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
  const client = page.locator('#client-input');
  const pet = page.locator('#pet-input');

  await client.fill('Mary');
  await page.getByText('Mary Theresa Jeffries').click();
  await pet.fill('Las');
  await page.getByText('Lassie').click();

  await client.fill('');
  await expect(client).toHaveValue('');
  await expect(pet).toBeDisabled();
  await expect(pet).toHaveAttribute('placeholder', 'Select a client first');
});

test('switching patients restores per-patient transcript history', async ({ page }) => {
  const answerRequests = [];
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
      const kind = new URL(url).searchParams.get('kind') || '';
      const clientId = new URL(url).searchParams.get('clientId') || '';
      const body = kind === 'client'
        ? { items: [{ id: 'client-1', label: 'Mary Theresa Jeffries', secondary: '8762', pet_count: 3 }] }
        : clientId === 'client-1'
          ? { items: [
              { id: 'pet-4', label: 'Emmett Bleu (#4)', secondary: 'Canine · Mixed', species: 'Canine', breed: 'Mixed' },
              { id: 'pet-5', label: 'Charlie Brown', secondary: 'Canine · Beagle', species: 'Canine', breed: 'Beagle' },
            ] }
          : { items: [] };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
      return;
    }
    if (url.includes('/api/rag/answer')) {
      const body = JSON.parse(route.request().postData() || '{}');
      answerRequests.push(body);
      const patient = body.patient_context?.patient_name || '';
      const answer = patient.includes('Emmett')
        ? 'Emmett answer one.'
        : 'Charlie answer one.';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ answer, citations: [], references: [], citation_map: {}, elapsed_seconds: 0 }),
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
  const client = page.locator('#client-input');
  const pet = page.locator('#pet-input');
  const question = page.locator('#question');
  const ask = page.locator('#ask');
  const transcript = page.locator('#transcript');

  await client.fill('Mary');
  await page.getByText('Mary Theresa Jeffries').click();

  await pet.fill('Emm');
  await page.getByText('Emmett Bleu (#4)').click();
  await question.fill('How fat is he?');
  await ask.click();
  await expect.poll(() => answerRequests.length).toBe(1);
  await expect(answerRequests[0].conversation).toHaveLength(0);

  await pet.fill('Cha');
  await page.getByText('Charlie Brown').click();
  await question.fill('How fat is he?');
  await ask.click();
  await expect.poll(() => answerRequests.length).toBe(2);

  await pet.fill('Emm');
  await page.getByText('Emmett Bleu (#4)').click();
  await expect(answerRequests).toHaveLength(2);
});

test('identical sequential questions are ignored and reopening a patient restores the prior thread', async ({ page }) => {
  const answerRequests = [];

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
      const kind = new URL(url).searchParams.get('kind') || '';
      const clientId = new URL(url).searchParams.get('clientId') || '';
      const query = new URL(url).searchParams.get('q') || '';
      const body = kind === 'client'
        ? { items: [{ id: 'client-1', label: 'Mary Theresa Jeffries', secondary: '8762', pet_count: 2 }] }
        : clientId === 'client-1'
          ? { items: [
              { id: 'pet-4', label: 'Emmett Bleu (#4)', secondary: 'Canine · Mixed', species: 'Canine', breed: 'Mixed' },
              { id: 'pet-5', label: 'Charlie Brown', secondary: 'Canine · Beagle', species: 'Canine', breed: 'Beagle' },
            ] }
          : { items: [] };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
      return;
    }
    if (url.includes('/api/rag/answer')) {
      const body = JSON.parse(route.request().postData() || '{}');
      answerRequests.push(body);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ answer: `Answer ${answerRequests.length}.`, citations: [], references: [], citation_map: {}, elapsed_seconds: 0 }),
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
  const client = page.locator('#client-input');
  const pet = page.locator('#pet-input');
  const question = page.locator('#question');
  const ask = page.locator('#ask');
  const transcript = page.locator('#transcript');

  await client.fill('Mary');
  await page.getByText('Mary Theresa Jeffries').click();

  await pet.fill('Emm');
  await page.getByText('Emmett Bleu (#4)').click();
  await question.fill('How fat is he?');
  await ask.click();
  await expect(transcript).toContainText('Answer 1.');
  await expect.poll(() => answerRequests.length).toBe(1);

  await question.fill('How fat is he?');
  await ask.click();
  await expect(transcript).toContainText('Answer 1.');
  await expect(transcript).not.toContainText('Answer 2.');
  await expect.poll(() => answerRequests.length).toBe(1);

  await pet.fill('Cha');
  await page.getByText('Charlie Brown').click();
  await question.fill('How old is he?');
  await ask.click();
  await expect(transcript).toContainText('Answer 2.');

  await pet.fill('Emm');
  await page.getByText('Emmett Bleu (#4)').click();
await expect(transcript).toContainText('How fat is he?');
  await expect(transcript).toContainText('Answer 1.');
  await expect(transcript).not.toContainText('Answer 2.');
});

test('composer stays visible while editing the client query and only hides on actual client change', async ({ page }) => {
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
      const params = new URL(url).searchParams;
      const kind = params.get('kind') || '';
      const clientId = params.get('clientId') || '';
      const query = (params.get('q') || '').toLowerCase();
      if (kind === 'client') {
        const items = query.startsWith('ma')
          ? [
              { id: 'client-1', label: 'Mary Theresa Jeffries', secondary: '8762' },
              { id: 'client-2', label: 'Martha Bell', secondary: '9911' },
            ]
          : query.startsWith('jo')
            ? [{ id: 'client-3', label: 'John Example', secondary: '2222' }]
            : [];
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items }),
        });
        return;
      }
      if (kind === 'pet' && clientId === 'client-1') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [{ id: 'pet-1', label: 'Lassie', secondary: 'Canine · Collie', species: 'Canine', breed: 'Collie' }],
          }),
        });
        return;
      }
      if (kind === 'pet' && clientId === 'client-3') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        });
        return;
      }
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
  const client = page.locator('#client-input');
  const composer = page.locator('#composer');
  const clientMenu = page.locator('#client-menu');
  const pet = page.locator('#pet-input');

  await client.fill('Mary Theresa Jeffries');
  await page.getByText('Mary Theresa Jeffries').click();
  await expect(composer).toBeVisible();
  await expect(pet).toBeEnabled();

  await client.fill('Mary T');
  await expect(client).toHaveValue('Mary T');
  await expect(composer).toBeVisible();
  await expect(pet).toBeEnabled();

  await client.fill('John Example');
  await page.getByText('John Example').click();
  await expect(composer).toBeVisible();
  await expect(pet).toBeEnabled();

  await client.fill('Mary Theresa Jeffries');
  await page.getByText('Mary Theresa Jeffries').click();
  await expect(composer).toBeVisible();
  await expect(pet).toBeEnabled();
  await expect(clientMenu).toBeHidden();
});
