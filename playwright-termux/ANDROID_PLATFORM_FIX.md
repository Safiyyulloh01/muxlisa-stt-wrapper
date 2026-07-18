# Playwright-Termux: Android Platform Workaround

## Root Cause

`playwright-core` >= 1.55.0 has a regression (issue #41852) where it checks `process.platform` at module load time in `coreBundle.js` **before** the `PLAYWRIGHT_BROWSERS_PATH=0` env override is evaluated. Since Android returns `"android"` (not `"linux"`), it throws:

```
Error: Unsupported platform: android
```

## The Fix

Two things are needed — they appear together in the repo's `package.json`:

### 1. Pin `playwright-core` to `1.54.1` (exact, no caret)

`^1.54.1` resolves to 1.61.1 which has the regression. Pinning to exactly `1.54.1` avoids it entirely since that version predates the regression.

```json
"dependencies": {
  "playwright-core": "1.54.1"
}
```

### 2. Set these env vars (in `.env` loaded by `dotenv`)

```
PLAYWRIGHT_BROWSERS_PATH=0
CHROMIUM_PATH=/data/data/com.termux/files/usr/bin/chromium-browser
```

- `PLAYWRIGHT_BROWSERS_PATH=0` tells Playwright to skip downloading its own browser binaries.
- `CHROMIUM_PATH` points to Termux's system Chromium (installed via `pkg install chromium` from the `x11-repo`).

### 3. Pass `executablePath` when launching

In `index.js`:

```js
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH,
  headless: true,
  args: ['--no-sandbox', '--disable-gpu']
});
```

This bypasses Playwright's internal browser lookup entirely.

## Alternative (for newer playwright-core)

If you need a newer version, use the pnpm `patchedDependencies` approach from [xJonathanLEI/termux-playwright](https://github.com/xJonathanLEI/termux-playwright) — it patches `hostPlatform.js` to map `android` → `ubuntu24.04` and adds `"android"` alongside `"linux"` in registry checks.
