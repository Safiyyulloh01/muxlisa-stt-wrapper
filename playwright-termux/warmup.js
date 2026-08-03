#!/usr/bin/env node
/**
 * Profile warmer — browse muxlisa.uz like a human in the persistent profile.
 *
 * Run this a few times (or let it loop) BEFORE transcribing, so the browser
 * profile accumulates cookies, history, and session data — Google scores
 * familiar sessions higher than fresh ones.
 *
 * Usage:
 *   node warmup.js [minutes]     # default 2 minutes
 *
 * Tip: leave it running in the background while you work.
 */

require('dotenv/config');
const { chromium } = require('playwright-core');

const TARGET_URL = 'https://muxlisa.uz/en';
const PROFILE_DIR = process.env.PROFILE_DIR || (process.env.HOME + '/.muxlisa-profile');

const PAGES = [
  'https://muxlisa.uz/en',
  'https://muxlisa.uz/en/about',
  'https://muxlisa.uz/en/careers',
  'https://muxlisa.uz/en/pricing',
];

const sleep = ms => new Promise(r => setTimeout(r, ms));
const rand = (min, max) => min + Math.random() * (max - min);

async function humanScroll(page) {
  const steps = 4 + Math.floor(Math.random() * 8);
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, 100 + Math.random() * 400);
    await sleep(rand(150, 600));
  }
}

async function humanMove(page) {
  const moves = 3 + Math.floor(Math.random() * 5);
  for (let i = 0; i < moves; i++) {
    await page.mouse.move(rand(100, 1800), rand(100, 900));
    await sleep(rand(200, 800));
  }
}

(async () => {
  const fs = require('fs');
  if (!fs.existsSync(PROFILE_DIR)) fs.mkdirSync(PROFILE_DIR, { recursive: true });

  const minutes = parseFloat(process.argv[2] || '2');
  const deadline = Date.now() + minutes * 60000;

  console.error(`🌡 Warming profile for ${minutes} min...`);
  console.error(`   Profile: ${PROFILE_DIR}`);

  const context = await chromium.launchPersistentContext(PROFILE_DIR, {
    executablePath: process.env.CHROMIUM_PATH,
    headless: true,
    timeout: 60000,
    viewport: { width: 1920, height: 1080 },
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
    locale: 'en-US',
    timezoneId: 'Asia/Tashkent',
    colorScheme: 'light',
    args: [
      '--headless=new', '--no-sandbox', '--disable-gpu',
      '--disable-crashpad', '--disable-breakpad', '--disable-dev-shm-usage',
      '--disable-setuid-sandbox', '--no-first-run', '--no-zygote',
      '--disable-blink-features=AutomationControlled',
      '--window-size=1920,1080',
    ],
  });

  const page = await context.newPage();

  let visited = 0;
  while (Date.now() < deadline) {
    const url = PAGES[Math.floor(Math.random() * PAGES.length)];
    try {
      await page.goto(url, { waitUntil: 'load', timeout: 30000 });
      await sleep(rand(1000, 3000));
      await humanScroll(page);
      await humanMove(page);
      await sleep(rand(1500, 5000));
      visited++;
      console.error(`✓ Visited ${url} (${visited} total)`);
    } catch (e) {
      console.error(`⚠ ${url}: ${e.message}`);
    }
    await sleep(rand(2000, 5000));
  }

  console.error(`\n✅ Warmup done — ${visited} page visits, profile is warmer.`);
  await context.close();
})().catch(err => { console.error('ERROR:', err.message); process.exit(1); });
