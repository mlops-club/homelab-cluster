// Purpose: Outside-in browser check of the public Audiobookshelf login page, with Web Vitals
// Scope: Grafana POC test 3. Runs from a Grafana public probe; also runs locally with `k6 run`
import { browser } from 'k6/browser';
import { check } from 'k6';

export const options = {
  scenarios: {
    ui: { executor: 'shared-iterations', options: { browser: { type: 'chromium' } } },
  },
  thresholds: { checks: ['rate==1'] },
};

export default async function () {
  const page = await browser.newPage();
  try {
    await page.goto('https://books.mlops-club.org/login', { waitUntil: 'networkidle' });
    const login = page.locator('input[type="password"]');
    await login.waitFor({ state: 'visible', timeout: 10000 });
    check(await page.title(), { 'audiobookshelf login page': (t) => t.toLowerCase().includes('audiobookshelf') });
  } finally {
    await page.close();
  }
}
