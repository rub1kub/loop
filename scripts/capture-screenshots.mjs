import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const output = path.join(root, 'docs', 'screenshots');
const origin = 'http://127.0.0.1:4173';
const preview = spawn(
  'npm',
  [
    '--workspace',
    '@loop/web',
    'exec',
    'vite',
    'preview',
    '--',
    '--host',
    '127.0.0.1',
    '--port',
    '4173',
  ],
  { cwd: root, stdio: 'ignore' },
);

async function waitForPreview() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(origin);
      if (response.ok) return;
    } catch {
      // The preview process is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error('Vite preview did not start');
}

async function capture(page, name, screen, action) {
  await page.goto(`${origin}/?screen=${screen}`);
  if (screen !== 'loader') {
    await page.waitForSelector('.screen, .onboarding, .inline-preview');
    await page.waitForTimeout(300);
  }
  if (action) await action(page);
  await page.screenshot({ path: path.join(output, `${name}.png`) });
}

try {
  await mkdir(output, { recursive: true });
  await waitForPreview();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });

  await capture(page, 'loader', 'loader');
  await capture(page, 'onboarding', 'onboarding');
  await capture(page, 'onboarding-bank', 'onboarding-bank');
  await capture(page, 'onboarding-duel', 'onboarding-duel');
  await capture(page, 'bank-empty', 'bank-empty');
  await capture(page, 'bank-active', 'bank-active');
  await capture(page, 'bank-create-position', 'bank-empty', async (current) => {
    await current.getByRole('button', { name: 'НАЧАТЬ ЦИКЛ', exact: true }).click();
    await current.getByLabel('Сумма в GRAM').fill('2');
    await current.getByRole('button', { name: /ДАЛЬШЕ/ }).click();
    await current.getByRole('button', { name: /×1.5/ }).click();
    await current.getByRole('button', { name: 'ПРОВЕРИТЬ' }).click();
    await current.waitForTimeout(300);
  });
  await capture(page, 'duel-create', 'duel-create');
  await capture(page, 'duel-matchmaking', 'duel-matchmaking');
  await capture(page, 'duel-invite', 'duel-invite');
  await capture(page, 'duel-result', 'duel-result');
  await capture(page, 'rating', 'rating');
  await capture(page, 'profile', 'profile');
  await capture(page, 'settings', 'settings');
  await capture(page, 'telegram-inline-duel', 'inline');

  await browser.close();
} finally {
  preview.kill('SIGTERM');
}
