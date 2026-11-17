import { test, expect, _electron as electron, ElectronApplication, Page } from '@playwright/test';
import { existsSync, mkdtempSync, rmSync } from 'fs';
import { homedir, tmpdir } from 'os';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

let electronApp: ElectronApplication;
let window: Page;
const dataDir = mkdtempSync(join(tmpdir(), 'corvus-e2e-'));

// Scripted provider (backend/corvus/llm/scripted.py): deterministic replies,
// and "e2e create folder <path>" emits a medium-risk create_folder call.
test.describe('Corvus Desktop E2E', () => {
  test.describe.configure({ mode: 'serial', timeout: 120_000 });
  test.beforeAll(async () => {
    electronApp = await electron.launch({
      args: [join(__dirname, '../../dist-electron/main.cjs')],
      env: { ...process.env, CORVUS_TEST_PROVIDER: 'scripted', CORVUS_DATA_DIR: dataDir },
    });
    // The widget and overlay windows load "#/widget" / "#/overlay"; the main one has no hash.
    const isMain = (p: Page) => /^(file|http)/.test(p.url()) && !/#\/(widget|overlay)/.test(p.url());
    await expect.poll(() => electronApp.windows().some(isMain), { timeout: 60_000 }).toBe(true);
    window = electronApp.windows().find(isMain)!;
    await window.waitForLoadState('domcontentloaded');
  });

  test.afterAll(async () => {
    await electronApp?.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  test('app launches and a window opens', async () => {
    expect(electronApp.windows().length).toBeGreaterThan(0);
    expect(window.url()).not.toBe('about:blank');
  });

  test('onboarding can be skipped on a fresh profile', async () => {
    const skip = window.getByRole('button', { name: 'Skip for now' });
    await expect(skip).toBeVisible({ timeout: 60_000 });
    await skip.click();
    await expect(window.getByPlaceholder('Message Corvus...')).toBeVisible({ timeout: 30_000 });
  });

  test('chat message gets a reply', async () => {
    const input = window.getByPlaceholder('Message Corvus...');
    await input.fill('hello there');
    await input.press('Enter');
    await expect(window.getByText('Scripted reply: hello there')).toBeVisible({ timeout: 30_000 });
  });

  for (const approve of [false, true]) {
    test(`confirmation card ${approve ? 'approve runs' : 'cancel blocks'} the action`, async () => {
      const target = join(homedir(), `corvus-e2e-${approve ? 'yes' : 'no'}-${Date.now()}`);
      try {
        const input = window.getByPlaceholder('Message Corvus...');
        await input.fill(`e2e create folder ${target}`);
        await input.press('Enter');
        const button = window.getByRole('button', { name: approve ? 'Yes, do it' : 'Cancel' });
        await expect(button).toBeVisible({ timeout: 30_000 });
        await button.click();
        await expect(window.getByText('Done.').last()).toBeVisible({ timeout: 30_000 });
        expect(existsSync(target)).toBe(approve);
      } finally {
        rmSync(target, { recursive: true, force: true });
      }
    });
  }
});
