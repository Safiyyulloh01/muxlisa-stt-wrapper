# Muxlisa STT Wrapper

Turn [Muxlisa.uz](https://muxlisa.uz/en)'s free Uzbek STT demo into your own API service.

## Quick Start

```bash
git clone <this-repo>
cd ttsdemo

# Install everything (detects Termux/Android vs Linux)
bash install.sh

# Start the API service
./run.sh

# In another terminal — transcribe audio
python3 transcribe.py speech.wav
```

## API Service

```bash
./run.sh                            # start on :8000
CAPSOLVER_API_KEY="key" ./run.sh    # use Capsolver for higher reCAPTCHA scores

curl -X POST http://localhost:8000/v1/transcribe \
  -F "audio=@speech.wav"

curl http://localhost:8000/v1/health     # health check
curl http://localhost:8000/v1/status     # server status
```

The demo accepts WAV audio up to ~10 seconds per chunk. Longer files are
**automatically split at silence boundaries** (not mid-word), transcribed
per chunk, and merged.

```json
{
  "status": "ok",
  "transcript": "full transcribed text...",
  "duration_sec": 33.0,
  "chunks": 4
}
```

## One-shot CLI

```bash
python3 transcribe.py speech.wav              # auto (Playwright Chromium)
CAPSOLVER_API_KEY="key" python3 transcribe.py speech.wav  # higher score
python3 transcribe.py speech.wav --dry-run    # test Unique-Key generation
python3 transcribe.py speech.wav --json       # full JSON output
```

## Browser Warming (important for reCAPTCHA scores)

Google scores reCAPTCHA by how "familiar" your browser + IP look. A
fresh headless browser scores ~0.1-0.3 (rejected by the demo). Warming
it up gets scores that pass.

### 1. Persistent profile

The browser keeps its profile at `~/.muxlisa-profile` between runs —
cookies, history, and localStorage accumulate, so each session is more
familiar than the last. Nothing to do; it just works.

### 2. Warm up the profile

```bash
cd playwright-termux
node warmup.js 5    # browses muxlisa.uz like a human for 5 minutes
```

Run it a few times before transcribing (or leave it looping). Random
scroll, mouse movement, and delays make it look like a real visitor.

### 3. Export cookies from your real browser (biggest boost)

1. Open **muxlisa.uz** in your phone's/desktop's Chrome
2. Browse around, read the demo, scroll for a minute
3. Export cookies (DevTools → Application → Cookies, or an extension)
4. Save them to `~/.muxlisa-cookies.json`:

```json
[
  {"name": "NID", "value": "...", "domain": ".google.com"},
  {"name": "_ga", "value": "...", "domain": ".muxlisa.uz"}
]
```

The automation injects them before loading the page — Google sees the
same session that was already browsing, and the score jumps.

### 4. Token server (fast tokens)

`run.sh` auto-starts a persistent token daemon (`token_server.js`) that
keeps the warmed browser open. Instead of launching Chromium (~15-20s)
per request, each transcription gets a **fresh** reCAPTCHA token in
~2s. Tokens are single-use, so a new one is fetched every request.

Manual start: `cd playwright-termux && node token_server.js`

## Captcha Provider Configuration

The service uses captcha solving services to get reCAPTCHA tokens.

### Interactive setup menu

```bash
./setup_captcha.sh
```

Arrow keys ↑/↓ to navigate, descriptions update as you move, Enter to
select a provider, type the API key, Enter confirms. The chosen provider
is saved as the default in `.env`.

### Providers

| Provider | Env var | Cost |
|---|---|---|
| Nopecha | `NOPECHA_API_KEY` | Free (5 solves/day via GitHub sign-in) |
| NoCaptchaAI | `NOCAPTCHA_API_KEY` | Free (200/day claimed) |
| Capsolver | `CAPSOLVER_API_KEY` | Paid (~$0.002/solve) |
| CaptchaAI | `CAPTCHAAI_API_KEY` | Paid (~$15/mo, trial via ticket) |
| 2Captcha | `TWOCAPTCHA_API_KEY` | Paid (~$1-3/1000) |
| Playwright | *(no key)* | Free (local Chromium, needs warming) |

### Choosing the default provider

Set `CAPTCHA_PROVIDER` in `playwright-termux/.env`:

```bash
CAPTCHA_PROVIDER=playwright      # use warmed local browser
CAPTCHA_PROVIDER=nopecha         # or nocaptchaai | captchaai | capsolver | twocaptcha
```

Or via env var (overrides .env):

```bash
CAPTCHA_PROVIDER=playwright ./run.sh
```

### Priority order (if CAPTCHA_PROVIDER unset)

1. Nopecha → 2. NoCaptchaAI → 3. CaptchaAI → 4. Capsolver → 5. 2Captcha → 6. Playwright

The service uses the **first provider with a valid key**. If a solver
fails (bad key, etc.), it warns and tries the next one automatically.

### Quick setup without the menu

```bash
echo "CAPTCHA_PROVIDER=playwright" >> playwright-termux/.env
# or add an API key:
echo "NOPECHA_API_KEY=your-key" >> playwright-termux/.env
```

Restart `./run.sh` after changes. The startup banner shows which
provider is active.

## How It Works

The Muxlisa frontend was reverse-engineered to extract:

| Component | Detail |
|---|---|
| **Demo API** | `POST https://api.muxlisa.uz/v1/api/services/stt-demo/` |
| **Auth** | `Unique-Key: MD5("b01b6852888f401689483814d4e1e6e0f68" + MD5(filename))` |
| **Form** | `file` (WAV), `g-recaptcha-v3`, `g-recaptcha-v2` |
| **reCAPTCHA v3 key** | `6LfrVHopAAAAALEkxrmPZsw1vRpAvcc8f1nn7EcY` |

## Audio Chunking

The demo API enforces ~10 seconds per request. For longer files, the engine:

1. **Loads** audio via ffmpeg (WAV, MP3, FLAC, OGG, M4A) as mono 16-bit 16kHz PCM
2. **Finds silence** by computing RMS energy with a 50ms sliding window, estimating noise floor (5th percentile), and setting a threshold at 3× noise floor
3. **Splits near boundaries** — for each 10-second boundary, it searches ±300ms for the lowest-energy frame and cuts there, so words are never cropped
4. **Transcribes** each chunk through the demo API
5. **Merges** results with spaces

```bash
# Dry-run to see where splits would happen:
python3 transcribe.py long-speech.wav --dry-run

# Output:
# Duration: 33.0s → 4 chunk(s)
#   0.0s → 9.7s  (9.7s)
#   9.7s → 19.4s (9.7s)
#   19.4s → 29.5s (10.1s)
#   29.5s → 33.0s (3.5s)
```

## reCAPTCHA: Two Methods

| Method | Score | Cost | Setup |
|---|---|---|---|
| **Playwright** | 0.3 (may be rejected) | Free | Chromium installed by install.sh |
| **Capsolver API** | 0.7-0.9 ✅ | ~$0.002/solve | Get key at [capsolver.com](https://capsolver.com) ($1 free) |

Set the Capsolver key via env var or `.env`:
```bash
export CAPSOLVER_API_KEY="CAP-..."
# or add to playwright-termux/.env:
# CAPSOLVER_API_KEY=CAP-...
```

## Files

| File | Purpose |
|---|---|
| `transcribe.py` | Core engine — CLI + library |
| `service.py`    | FastAPI server |
| `install.sh`    | Platform-aware installer |
| `run.sh`        | Start the API service |
| `requirements.txt` | Python deps |
| `playwright-termux/` | Node.js Playwright for reCAPTCHA |
