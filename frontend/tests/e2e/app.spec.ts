import { test, expect, _electron as electron, ElectronApplication, Page } from '@playwright/test';
import { join } from 'path';

let electronApp: ElectronApplication;
let window: Page;

test.describe('Corvus Desktop E2E', () => {
  test.beforeAll(async () => {
    electronApp = await electron.launch({
      args: [join(__dirname, '../../dist-electron/main.cjs')],
    });
    
    // Wait for the first window to appear
    window = await electronApp.firstWindow();
    
    // Wait for the React app to load
    await window.waitForLoadState('domcontentloaded');
  });

  test.afterAll(async () => {
    if (electronApp) {
      await electronApp.close();
    }
  });

  test('app launches and displays the onboarding or main interface', async () => {
    const title = await window.title();
    expect(title).toBe('Corvus');

    // We either see the main app shell or the onboarding wizard
    const isMainApp = await window.locator('nav').count() > 0;
    const isOnboarding = await window.locator('text=Corvus').count() > 0 || await window.locator('text=How to use Corvus').count() > 0;
    
    expect(isMainApp || isOnboarding).toBeTruthy();
  });
});
