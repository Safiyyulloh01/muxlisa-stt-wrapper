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

The demo accepts WAV audio, max ~10 seconds. Output:

```json
{
  "status": "ok",
  "transcript": "transcribed text in Uzbek",
  "audio_duration_sec": 3
}
```

## One-shot CLI

```bash
python3 transcribe.py speech.wav              # auto (Playwright Chromium)
CAPSOLVER_API_KEY="key" python3 transcribe.py speech.wav  # higher score
python3 transcribe.py speech.wav --dry-run    # test Unique-Key generation
python3 transcribe.py speech.wav --json       # full JSON output
```

## How It Works

The Muxlisa frontend was reverse-engineered to extract:

| Component | Detail |
|---|---|
| **Demo API** | `POST https://api.muxlisa.uz/v1/api/services/stt-demo/` |
| **Auth** | `Unique-Key: MD5("b01b6852888f401689483814d4e1e6e0f68" + MD5(filename))` |
| **Form** | `file` (WAV), `g-recaptcha-v3`, `g-recaptcha-v2` |
| **reCAPTCHA v3 key** | `6LfrVHopAAAAALEkxrmPZsw1vRpAvcc8f1nn7EcY` |

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
