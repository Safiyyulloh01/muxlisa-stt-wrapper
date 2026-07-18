#!/usr/bin/env node
/**
 * Get reCAPTCHA v3 token from Muxlisa.uz using Playwright + Termux Chromium.
 *
 * Usage:
 *   CHROMIUM_PATH=/data/data/com.termux/files/usr/bin/chromium-browser \
 *     node get_token.js [site_key] [action]
 *
 * Output: the token string to stdout
 */

require('dotenv/config');
const { chromium } = require('playwright-core');

const SITE_KEY  = process.argv[2] || '6LfrVHopAAAAALEkxrmPZsw1vRpAvcc8f1nn7EcY';
const ACTION    = process.argv[3] || 'enquiryFormSubmit';
const TARGET_URL = 'https://muxlisa.uz/en';

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH,
    headless: true,
    timeout: 60000,
    args: [
      '--no-sandbox',
      '--disable-gpu',
      '--disable-crashpad',
      '--disable-breakpad',
      '--disable-dev-shm-usage',
      '--disable-setuid-sandbox',
      '--no-first-run',
      '--no-zygote',
      '--single-process',
      '--disable-blink-features=AutomationControlled',
    ],
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
    locale: 'en-US',
    timezoneId: 'Asia/Tashkent',
    geolocation: { latitude: 41.2995, longitude: 69.2401 },
    permissions: ['geolocation'],
  });

  const page = await context.newPage();

  // Remove automation traces
  await page.addInitScript(() => {
    delete navigator.__proto__.webdriver;
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    // Override plugins
    Object.defineProperty(navigator, 'plugins', {
      get: () => [1, 2, 3, 4, 5],
    });
    // Override languages
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en'],
    });
  });

  await page.goto(TARGET_URL, { waitUntil: 'load', timeout: 30000 });

  const token = await page.evaluate(async ({ key, action }) => {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = `https://www.google.com/recaptcha/api.js?render=${key}`;
      script.onload = () => {
        grecaptcha.ready(async () => {
          try {
            const t = await grecaptcha.execute(key, { action });
            resolve(t);
          } catch (e) {
            reject(e.message);
          }
        });
      };
      script.onerror = () => reject('Failed to load reCAPTCHA script');
      document.head.appendChild(script);
    });
  }, { key: SITE_KEY, action: ACTION });

  console.log(token);
  await browser.close();
})().catch(err => {
  console.error('ERROR:', err.message);
  process.exit(1);
});
