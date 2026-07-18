require('dotenv/config');
const { chromium } = require('playwright-core');

const run = async () => {
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
      '--single-process'
    ]
  });

  const page = await browser.newPage();
  await page.goto('https://github.com/microsoft/playwright', { timeout: 30000 });
  const title = await page.title();
  console.log(`Page title: ${title}`);

  await browser.close();
};

run().catch(console.error);
