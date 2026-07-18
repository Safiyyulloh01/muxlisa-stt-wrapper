#!/usr/bin/env python3
"""
Muxlisa STT API Service — FastAPI Server

Wraps the Muxlisa.uz free STT demo into a proper REST API.
Handles reCAPTCHA automatically via Playwright or Capsolver.

Usage:
  python3 service.py                          # start server (port 8000)
  python3 service.py --port 8080              # custom port
  CAPSOLVER_API_KEY="key" python3 service.py  # use Capsolver for higher scores

API:
  POST /v1/transcribe  — Upload audio, get transcription
  GET  /v1/health      — Health check
  GET  /v1/status      — Server status & config
"""

import json, logging, os, sys, time
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import JSONResponse
import uvicorn

# Import the core engine
sys.path.insert(0, str(Path(__file__).parent))
from transcribe import transcribe, get_token, compute_unique_key, convert_audio, DEMO_ENDPOINT

# ── Logging ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("muxlisa")

# ── App ────────────────────────────────────────────────────────

app = FastAPI(
    title="Muxlisa STT API",
    description="Free Uzbek speech-to-text via Muxlisa.uz demo. "
                "Automatically handles reCAPTCHA via Playwright or Capsolver.",
    version="3.0.0",
    docs_url="/docs",
)

REQUEST_COUNT = 0
START_TIME = time.time()


# ── Middleware ──────────────────────────────────────────────────

@app.middleware("http")
async def count_requests(request: Request, call_next):
    global REQUEST_COUNT
    REQUEST_COUNT += 1
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    log.info(f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.2f}s)")
    return response


# ── Routes ─────────────────────────────────────────────────────

@app.get("/v1/health")
def health():
    """Health check."""
    return {"status": "ok", "timestamp": time.time()}


@app.get("/v1/status")
def status():
    """Server status and configuration."""
    env = {}
    env_file = Path(__file__).parent / "playwright-termux" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v[:20] + "..." if len(v) > 20 else v

    # Check Chromium
    chromium_path = env.get("CHROMIUM_PATH") or os.environ.get("CHROMIUM_PATH")
    chromium_ok = chromium_path and os.path.exists(chromium_path)

    return {
        "server": {
            "uptime_sec": int(time.time() - START_TIME),
            "requests_served": REQUEST_COUNT,
        },
        "recaptcha": {
            "nopecha": bool(os.environ.get("NOPECHA_API_KEY")),
            "nocaptchaai": bool(os.environ.get("NOCAPTCHA_API_KEY")),
            "capsolver": bool(os.environ.get("CAPSOLVER_API_KEY")),
            "playwright": chromium_ok,
            "chromium_path": chromium_path,
        },
        "endpoint": DEMO_ENDPOINT,
        "docs": "/docs",
    }


@app.post("/v1/transcribe")
async def transcribe_route(
    audio: UploadFile = File(...),
    recaptcha_token: Optional[str] = Form(None),
    max_seconds: Optional[int] = Form(10),
):
    """
    Transcribe Uzbek speech to text.
    
    Upload a WAV audio file (max ~10 seconds for the demo tier).
    reCAPTCHA is handled automatically via Playwright or Capsolver
    if not provided.
    
    Returns:
      - 200: { status: "ok", transcript: "...", audio_duration_sec: N }
      - 4xx/5xx: { error: "...", detail: "..." }
    """
    # Validate input
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "Empty audio file")
    if len(audio_bytes) > 50 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 50 MB)")

    # Save to temp file
    import tempfile, os
    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        result = transcribe(tmp_path, recaptcha_token=recaptcha_token, verbose=False)
    except Exception as e:
        raise HTTPException(500, f"Internal error: {e}")
    finally:
        os.unlink(tmp_path)

    status_code = result.get("status_code", 500)

    if status_code == 200:
        return {
            "status": "ok",
            "transcript": result.get("transcript"),
            "duration_sec": result.get("duration_sec"),
            "chunks": result.get("num_chunks", 1),
        }
    else:
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": result.get("error", "Unknown error"),
            }
        )


@app.post("/v1/token")
async def get_recaptcha_token():
    """
    Get a fresh reCAPTCHA v3 token.
    Useful for debugging or manual integration.
    """
    token, err = get_token()
    if err:
        raise HTTPException(502, f"Token error: {err}")
    return {"token": token}


# ── Main ───────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")

    print("─" * 50)
    print("  Muxlisa STT API Service")
    print("─" * 50)
    print(f"  Listen:  http://{host}:{port}")
    print(f"  Docs:    http://{host}:{port}/docs")
    print(f"  Endpoint: POST /v1/transcribe")
    print()
    print(f"  Nopecha:     {'✅' if os.environ.get('NOPECHA_API_KEY') else '❌'}  (5 free/day)")
  print(f"  NoCaptchaAI: {'✅' if os.environ.get('NOCAPTCHA_API_KEY') else '❌'}  (200 free/day)")
  print(f"  Capsolver:   {'✅' if os.environ.get('CAPSOLVER_API_KEY') else '❌'}")
    print(f"  Playwright: {'✅' if os.path.exists(os.environ.get('CHROMIUM_PATH', '/data/data/com.termux/files/usr/bin/chromium-browser')) else '❌'}")
    print("─" * 50)

    uvicorn.run(app, host=host, port=port, log_level="info")
