import { test, expect, _electron as electron, ElectronApplication, Page } from '@playwright/test';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

let electronApp: ElectronApplication;
let window: Page;

test.describe('Corvus Desktop E2E', () => {
  test.beforeAll(async () => {
    electronApp = await electron.launch({
      args: [join(__dirname, '../../dist-electron/main.cjs')],
    });

    // Wait for the first window to appear
    window = await electronApp.firstWindow();

    // Wait for the page to finish loading
    await window.waitForLoadState('domcontentloaded');
  });

  test.afterAll(async () => {
    if (electronApp) {
      await electronApp.close();
    }
  });

  test('app launches successfully and a window opens', async () => {
    // Verify the Electron app created a window
    const windows = electronApp.windows();
    expect(windows.length).toBeGreaterThan(0);

    // Verify the window has a valid URL (either dev server or file://)
    const url = window.url();
    expect(url).toBeTruthy();
    expect(url).not.toBe('about:blank');
  });
});
