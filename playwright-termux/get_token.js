#!/usr/bin/env node
/**
 * Get reCAPTCHA v3 token via Playwright + Chromium with full stealth.
 *
 * Anti-detection measures:
 *   - Removes navigator.webdriver and all automation flags via CDP
 *   - Spoofs navigator.plugins, mimeTypes, hardwareConcurrency, deviceMemory
 *   - Sets realistic viewport, timezone, geolocation, locale
 *   - Rotates User-Agent from a pool of clean browser strings
 *   - Hides headless Chrome-specific WebGL/Canvas anomalies
 *   - Patches chrome.runtime and other Chrome internals
 *
 * Usage:
 *   CHROMIUM_PATH=/path/to/chromium node get_token.js [site_key] [action]
 *
 * Output: the reCAPTCHA v3 token to stdout
 */

require('dotenv/config');
const { chromium } = require('playwright-core');

const SITE_KEY   = process.argv[2] || '6LfrVHopAAAAALEkxrmPZsw1vRpAvcc8f1nn7EcY';
const ACTION     = process.argv[3] || 'enquiryFormSubmit';
const TARGET_URL = 'https://muxlisa.uz/en';

// ── User-Agent pool (rotate for each call) ──────────────────────────────

const USER_AGENTS = [
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
];

const UA = USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];

// ── Stealth init script (runs before every page load) ───────────────────

const STEALTH_SCRIPT = `
// 1. Remove webdriver
delete Object.getPrototypeOf(navigator).webdriver;
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. Spoof plugins
Object.defineProperty(navigator, 'plugins', {
  get: () => [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
    { name: 'Native Client',     filename: 'internal-nacl-plugin'  },
  ],
});

// 3. Spoof mimeTypes
Object.defineProperty(navigator, 'mimeTypes', {
  get: () => [
    { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
    { type: 'text/pdf',        suffixes: 'pdf', description: 'Portable Document Format' },
  ],
});

// 4. Hardware concurrency & memory (realistic)
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// 5. Languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// 6. Spoof chrome.runtime (detected by some bot checks)
if (!window.chrome) window.chrome = {};
if (!window.chrome.runtime) {
  window.chrome.runtime = {
    connect:        () => ({ onMessage: { addListener: () => {} }, postMessage: () => {} }),
    sendMessage:    () => {},
    getURL:         p => p,
    getManifest:    () => ({ version: '149.0.0.0' }),
    id: 'aohjmdhkmkdfmpjgekmcllkanoccnmpc',
  };
}

// 7. Override permissions query (headless returns 'none' for some APIs)
const origQuery = navigator.permissions.query;
navigator.permissions.query = async p => {
  if (p.name === 'notifications') return { state: 'prompt', onchange: null };
  if (p.name === 'clipboard-write') return { state: 'granted', onchange: null };
  return origQuery.call(navigator.permissions, p);
};

// 8. Spoof WebGL vendor/renderer (headless returns Google SwiftShader)
const getExt = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, attrs) {
  const ctx = getExt.call(this, type, attrs);
  if (ctx && type === 'webgl') {
    const getExt = ctx.getExtension;
    ctx.getExtension = function(name) {
      if (name === 'WEBGL_debug_renderer_info') return null;
      return getExt.call(ctx, name);
    };
  }
  return ctx;
};

// 9. Spoof screen orientation (headless returns angle:0)
if (screen.orientation) {
  Object.defineProperty(screen.orientation, 'angle', { get: () => 0 });
  Object.defineProperty(screen.orientation, 'type', { get: () => 'landscape-primary' });
}
`;


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

      // Suppress headless-specific diagnostic messages
      '--disable-background-networking',
      '--disable-default-apps',
      '--disable-sync',
      '--disable-translate',
      '--disable-client-side-phishing-detection',

      // Use a real WebGL GPU instead of SwiftShader
      '--enable-webgl',
      '--use-gl=angle',
      '--use-angle=swiftshader-webgl',
    ],
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    userAgent: UA,
    locale: 'en-US',
    timezoneId: 'Asia/Tashkent',
    geolocation: { latitude: 41.2995, longitude: 69.2401 },
    permissions: ['geolocation', 'notifications'],
    deviceScaleFactor: 1,
    hasTouch: false,
    isMobile: false,
    colorScheme: 'light',
    reducedMotion: 'no-preference',
    forcedColors: 'none',
  });

  const page = await context.newPage();

  // Apply stealth via CDP (stronger than addInitScript alone)
  await page.context().addInitScript(STEALTH_SCRIPT);

  // Also use CDP directly to remove automation flags at the protocol level
  const cdp = await context.newCDPSession(page);
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
    source: STEALTH_SCRIPT,
  });

  // Navigate
  await page.goto(TARGET_URL, { waitUntil: 'load', timeout: 30000 });

  // Small human-like delay before executing
  await new Promise(r => setTimeout(r, 500 + Math.random() * 1000));

  // Get reCAPTCHA token
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
