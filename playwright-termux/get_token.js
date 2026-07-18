#!/usr/bin/env node
/**
 * Get reCAPTCHA v3 token via Playwright + Chromium with maximum stealth.
 *
 * Implements all known evasion techniques:
 *   - CDP-level automation flag removal
 *   - Canvas/WebGL/font fingerprint spoofing
 *   - navigator patches (plugins, mimeTypes, hardwareConcurrency, deviceMemory)
 *   - chrome.runtime object injection
 *   - Human-like behavioral simulation (scroll, mouse move)
 *   - Realistic sec-ch-ua headers matching the User-Agent
 *   - New Headless mode (unified binary, same as headed)
 *   - No --single-process (multi-process matches real Chrome)
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

// ── User-Agent pool ──────────────────────────────────────────

const USER_AGENTS = [
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
];

const UA = USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];

// Detect platform from UA
const UA_PLATFORM = UA.includes('Windows') ? 'Win32' : UA.includes('Mac') ? 'MacIntel' : 'Linux x86_64';
const UA_PLATFORM_NAME = UA.includes('Windows') ? 'Windows' : UA.includes('Mac') ? 'macOS' : 'Linux';

// ── Stealth init script (injected via CDP, runs in main world) ──

const STEALTH_SCRIPT = `
// === 1. navigator.webdriver — remove at both levels ===
delete Object.getPrototypeOf(navigator).webdriver;
Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined,
  configurable: true,
  enumerable: true,
});

// === 2. navigator.plugins — realistic Chrome plugins ===
Object.defineProperty(navigator, 'plugins', {
  get: () => [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
  ],
});

// === 3. navigator.mimeTypes ===
Object.defineProperty(navigator, 'mimeTypes', {
  get: () => [
    { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
    { type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
  ],
});

// === 4. navigator.hardwareConcurrency & deviceMemory ===
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// === 5. navigator.languages ===
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// === 6. navigator.platform — must match User-Agent ===
Object.defineProperty(navigator, 'platform', { get: () => '${UA_PLATFORM}' });

// === 7. window.chrome — full Chrome runtime API ===
if (!window.chrome) window.chrome = {};
window.chrome.runtime = {
  connect:        () => ({ onMessage: { addListener: () => {} }, postMessage: () => {} }),
  sendMessage:    () => {},
  getURL:         p => p,
  getManifest:    () => ({ version: '149.0.0.0' }),
  id: 'aohjmdhkmkdfmpjgekmcllkanoccnmpc',
  onConnect:      { addListener: () => {} },
  onMessage:      { addListener: () => {} },
};
window.chrome.app = {
  isInstalled: false,
  InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
  RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
};
window.chrome.csi = () => ({
  onloadT: Date.now(), pageT: Date.now(), startE: Date.now(),
});
window.chrome.loadTimes = () => ({
  commitLoadTime: 0, finishDocumentLoadTime: 0, finishLoadTime: 0,
  firstPaintAfterLoadTime: 0, navigationType: 'BackForward',
  requestTime: 0, startLoadTime: 0, wasFetchedViaSpdy: false,
  wasNpnNegotiated: false, wasAlternateProtocolAvailable: false,
});

// === 8. Permissions API override ===
const origQuery = navigator.permissions.query.bind(navigator.permissions);
navigator.permissions.query = async p => {
  if (p.name === 'notifications') return { state: 'prompt', onchange: null };
  if (p.name === 'clipboard-write') return { state: 'granted', onchange: null };
  return origQuery(p);
};

// === 9. Canvas fingerprint noise ===
const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
const origToBlob = HTMLCanvasElement.prototype.toBlob;
HTMLCanvasElement.prototype.toDataURL = function(...args) {
  const ctx = this.getContext('2d');
  if (ctx) {
    const imgData = ctx.getImageData(0, 0, this.width, this.height);
    for (let i = 0; i < imgData.data.length; i += 4) {
      const noise = Math.random() * 0.5;
      imgData.data[i] = imgData.data[i] + noise | 0;
      imgData.data[i+1] = imgData.data[i+1] + noise | 0;
      imgData.data[i+2] = imgData.data[i+2] + noise | 0;
    }
    ctx.putImageData(imgData, 0, 0);
  }
  return origToDataURL.apply(this, args);
};

// === 10. WebGL vendor hiding ===
const origGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, attrs) {
  const ctx = origGetContext.call(this, type, attrs);
  if (ctx && (type === 'webgl' || type === 'experimental-webgl')) {
    const origGetParam = ctx.getParameter.bind(ctx);
    ctx.getParameter = function(param) {
      if (param === 37445) return 'Intel Inc.';          // UNMASKED_VENDOR_WEBGL
      if (param === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
      return origGetParam(param);
    };
    const origGetExt = ctx.getExtension.bind(ctx);
    ctx.getExtension = function(name) {
      if (name === 'WEBGL_debug_renderer_info') return null;
      return origGetExt(name);
    };
  }
  return ctx;
};

// === 11. Screen orientation ===
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
      '--headless=new',
      '--no-sandbox',
      '--disable-gpu',
      '--disable-crashpad',
      '--disable-breakpad',
      '--disable-dev-shm-usage',
      '--disable-setuid-sandbox',
      '--no-first-run',
      '--no-zygote',
      '--disable-blink-features=AutomationControlled',
      '--window-size=1920,1080',
      '--disable-background-networking',
      '--no-default-browser-check',
      '--disable-sync',
      '--enable-webgl',
      '--use-gl=angle',
      '--use-angle=swiftshader',
    ],
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    userAgent: UA,
    locale: 'en-US',
    timezoneId: 'Asia/Tashkent',
    geolocation: { latitude: 41.2995, longitude: 69.2401 },
    permissions: ['geolocation', 'notifications'],
    colorScheme: 'light',
    reducedMotion: 'no-preference',
    deviceScaleFactor: 1,
    hasTouch: false,
    isMobile: false,
    extraHTTPHeaders: {
      'Accept-Language': 'en-US,en;q=0.9',
      'sec-ch-ua': '"Chromium";v="149", "Not A(Brand";v="24", "Google Chrome";v="149"',
      'sec-ch-ua-mobile': '?0',
      'sec-ch-ua-platform': `"${UA_PLATFORM_NAME}"`,
    },
  });

  const page = await context.newPage();

  // Inject stealth via addInitScript (runs in main world before each page load)
  await context.addInitScript(STEALTH_SCRIPT);

  // Also inject via CDP (stronger, runs earlier)
  const cdp = await context.newCDPSession(page);
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
    source: STEALTH_SCRIPT,
  });

  // Override User-Agent at the CDP level too
  await cdp.send('Network.setUserAgentOverride', {
    userAgent: UA,
    acceptLanguage: 'en-US,en;q=0.9',
    platform: UA_PLATFORM,
  });

  // Set realistic device metrics
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 1920, height: 1080, deviceScaleFactor: 1,
    mobile: false, screenWidth: 1920, screenHeight: 1080,
    positionX: 0, positionY: 0,
    screenOrientation: { type: 'landscapePrimary', angle: 0 },
  });

  // Navigate
  await page.goto(TARGET_URL, { waitUntil: 'load', timeout: 30000 });

  // === Human-like behavioral simulation ===
  // Wait random time
  await new Promise(r => setTimeout(r, 800 + Math.random() * 1500));

  // Scroll down a bit (human-like, not instant)
  const scrollDist = 200 + Math.random() * 400;
  const scrollSteps = 5 + Math.floor(Math.random() * 8);
  for (let i = 0; i < scrollSteps; i++) {
    const delta = (scrollDist / scrollSteps) * (0.6 + Math.random() * 0.4);
    await page.mouse.wheel(0, delta);
    await new Promise(r => setTimeout(r, 80 + Math.random() * 120));
  }

  // Scroll back up a bit
  await new Promise(r => setTimeout(r, 300 + Math.random() * 600));
  const upSteps = 2 + Math.floor(Math.random() * 3);
  for (let i = 0; i < upSteps; i++) {
    await page.mouse.wheel(0, -(50 + Math.random() * 100));
    await new Promise(r => setTimeout(r, 60 + Math.random() * 100));
  }

  // Move mouse around like a human reading the page
  for (let i = 0; i < 3 + Math.floor(Math.random() * 4); i++) {
    const tx = 100 + Math.random() * 800;
    const ty = 200 + Math.random() * 600;
    const steps = 15 + Math.floor(Math.random() * 15);
    const startX = 500 + Math.random() * 200;
    const startY = 300 + Math.random() * 200;
    const cp1x = startX + (tx - startX) * 0.25 + (Math.random() - 0.5) * 60;
    const cp1y = startY + (ty - startY) * 0.25 + (Math.random() - 0.5) * 60;
    const cp2x = startX + (tx - startX) * 0.75 + (Math.random() - 0.5) * 60;
    const cp2y = startY + (ty - startY) * 0.75 + (Math.random() - 0.5) * 60;
    for (let s = 0; s <= steps; s++) {
      const t = s / steps;
      const u = 1 - t;
      const x = u*u*u*startX + 3*u*u*t*cp1x + 3*u*t*t*cp2x + t*t*t*tx;
      const y = u*u*u*startY + 3*u*u*t*cp1y + 3*u*t*t*cp2y + t*t*t*ty;
      await page.mouse.move(x, y);
      await new Promise(r => setTimeout(r, 5 + Math.random() * 15));
    }
    await new Promise(r => setTimeout(r, 200 + Math.random() * 600));
  }

  // Pause before getting token
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
