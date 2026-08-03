#!/usr/bin/env node
/**
 * Persistent reCAPTCHA token server.
 *
 * Keeps one warmed Chromium profile open, so getting a token is fast
 * (~1-2s instead of 15-20s browser launch) and the session stays warm
 * for better Google scores.
 *
 * Usage:
 *   node token_server.js [port]
 *
 * Endpoints:
 *   GET /token          → { token: "..." }   (fresh reCAPTCHA v3 token)
 *   GET /health         → { ok: true }
 *
 * The page is pre-warmed at muxlisa.uz; each /token call just runs
 * grecaptcha.execute() and returns the result. Tokens expire in ~2 min,
 * so call /token right before each transcription.
 */

require('dotenv/config');
const { chromium } = require('playwright-core');
const http = require('http');

const PORT = parseInt(process.argv[2] || process.env.TOKEN_SERVER_PORT || '9520', 10);
const SITE_KEY   = process.env.RECAPTCHA_SITE_KEY || '6LfrVHopAAAAALEkxrmPZsw1vRpAvcc8f1nn7EcY';
const ACTION     = process.env.RECAPTCHA_ACTION || 'enquiryFormSubmit';
const TARGET_URL = 'https://muxlisa.uz/en';
const PROFILE_DIR = process.env.PROFILE_DIR || (process.env.HOME + '/.muxlisa-profile');
const COOKIES_FILE = process.env.COOKIES_FILE || (process.env.HOME + '/.muxlisa-cookies.json');
const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36';

let page = null;
let browserReady = false;

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function warmup(page) {
  // Human-like: scroll a bit, move mouse, wait
  await sleep(400 + Math.random() * 800);
  const steps = 2 + Math.floor(Math.random() * 4);
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, 100 + Math.random() * 300);
    await sleep(120 + Math.random() * 200);
  }
  await page.mouse.move(200 + Math.random() * 600, 200 + Math.random() * 400);
  await sleep(300 + Math.random() * 500);
}

async function init() {
  const fs = require('fs');
  if (!fs.existsSync(PROFILE_DIR)) fs.mkdirSync(PROFILE_DIR, { recursive: true });

  const context = await chromium.launchPersistentContext(PROFILE_DIR, {
    executablePath: process.env.CHROMIUM_PATH,
    headless: true,
    timeout: 60000,
    viewport: { width: 1920, height: 1080 },
    userAgent: UA,
    locale: 'en-US',
    timezoneId: 'Asia/Tashkent',
    geolocation: { latitude: 41.2995, longitude: 69.2401 },
    permissions: ['geolocation', 'notifications'],
    colorScheme: 'light',
    reducedMotion: 'no-preference',
    deviceScaleFactor: 1,
    args: [
      '--headless=new', '--no-sandbox', '--disable-gpu',
      '--disable-crashpad', '--disable-breakpad', '--disable-dev-shm-usage',
      '--disable-setuid-sandbox', '--no-first-run', '--no-zygote',
      '--disable-blink-features=AutomationControlled',
      '--window-size=1920,1080',
    ],
  });

  // Inject real-browser cookies if provided
  try {
    if (fs.existsSync(COOKIES_FILE)) {
      const cookies = JSON.parse(fs.readFileSync(COOKIES_FILE, 'utf8'));
      if (Array.isArray(cookies) && cookies.length) {
        await context.addCookies(cookies.map(c => ({
          name: c.name, value: c.value,
          domain: c.domain || 'muxlisa.uz', path: c.path || '/',
        })));
        console.error(`✓ Injected ${cookies.length} cookies`);
      }
    }
  } catch (e) {
    console.error(`⚠ Cookie injection failed: ${e.message}`);
  }

  page = await context.newPage();
  await page.goto(TARGET_URL, { waitUntil: 'load', timeout: 30000 });
  await warmup(page);
  browserReady = true;
  console.error(`✓ Browser ready at ${TARGET_URL}`);
}

async function getToken() {
  if (!page) throw new Error('Browser not ready');
  return await page.evaluate(({ key, action }) => {
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = `https://www.google.com/recaptcha/api.js?render=${key}`;
      s.onload = () => {
        grecaptcha.ready(async () => {
          try {
            resolve(await grecaptcha.execute(key, { action }));
          } catch (e) { reject(e.message); }
        });
      };
      s.onerror = () => reject('reCAPTCHA load failed');
      document.head.appendChild(s);
    });
  }, { key: SITE_KEY, action: ACTION });
}

(async () => {
  await init();

  const server = http.createServer(async (req, res) => {
    const url = req.url.split('?')[0];

    if (url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: browserReady }));
      return;
    }

    if (url === '/token') {
      try {
        // Small human-like delay before each token
        await sleep(200 + Math.random() * 400);
        const token = await getToken();
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ token }));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
      return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'not found' }));
  });

  server.listen(PORT, '127.0.0.1', () => {
    console.error(`🖥 Token server running on http://127.0.0.1:${PORT}`);
    console.error(`   GET /token — fresh reCAPTCHA v3 token`);
    console.error(`   GET /health — status`);
  });
})().catch(err => {
  console.error('ERROR:', err.message);
  process.exit(1);
});
