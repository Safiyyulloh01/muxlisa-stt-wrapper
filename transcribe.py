#!/usr/bin/env python3
"""
Muxlisa STT Demo — Core Engine

Transcribes Uzbek speech to text using Muxlisa.uz's free demo API.
Handles reCAPTCHA token generation (Playwright or Capsolver), Unique-Key
computation (reverse-engineered from frontend JS), and audio conversion.

Usage:
  python3 transcribe.py audio.wav                        # auto (Playwright)
  CAPSOLVER_API_KEY="key" python3 transcribe.py audio.wav # higher score
  python3 transcribe.py audio.wav --token TOKEN           # manual token
"""

import hashlib, io, json, os, subprocess, sys, time
from pathlib import Path
from typing import Optional, Tuple

import requests

# ── Constants (from reverse-engineering the frontend) ──────────

DEMO_SALT = "b01b6852888f401689483814d4e1e6e0f68"
DEMO_ENDPOINT = "https://api.muxlisa.uz/v1/api/services/stt-demo/"
RECAPTCHA_SITE_KEY = "6LfrVHopAAAAALEkxrmPZsw1vRpAvcc8f1nn7EcY"
PAGE_URL = "https://muxlisa.uz/en"

# Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
PW_DIR = SCRIPT_DIR / "playwright-termux"
ENV_FILE = PW_DIR / ".env"
TOKEN_SCRIPT = PW_DIR / "get_token.js"
CHROMIUM_DEFAULT = "/data/data/com.termux/files/usr/bin/chromium-browser"


# ── Unique-Key Computation ─────────────────────────────────────

def compute_unique_key(filename: str) -> str:
    """
    Generates the Unique-Key header that the Muxlisa API expects.
    
    Reverse-engineered from frontend JavaScript:
      r = MD5(audio_file_name)
      key = MD5("b01b6852888f401689483814d4e1e6e0f68" + r)
    """
    r = hashlib.md5(filename.encode()).hexdigest()
    return hashlib.md5(f"{DEMO_SALT}{r}".encode()).hexdigest()


# ── Audio Processing ───────────────────────────────────────────

def convert_audio(path: str, max_sec: int = 10) -> bytes:
    """
    Convert any WAV file to 16-bit mono 16kHz.
    Truncates to max_sec seconds (demo limit is ~10s).
    Returns raw WAV bytes ready for upload.
    """
    import wave, array
    with wave.open(path, 'rb') as w:
        ch, sw, fr, nf = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(nf)

    duration = nf / fr
    if duration > max_sec:
        nf = int(fr * max_sec)
        raw = raw[:nf * ch * sw]

    # Convert to 16-bit mono
    if sw == 1:
        samples = array.array('h', (int((b - 128) * 256) for b in raw[::ch]))
    elif sw == 2:
        arr = array.array('h'); arr.frombytes(raw[:nf * ch * 2])
        samples = array.array('h', (arr[i] for i in range(0, len(arr), ch)))
    else:
        raise ValueError(f"Unsupported sample width: {sw}")

    # Resample to 16kHz
    if fr != 16000:
        ratio = 16000 / fr
        new_len = int(len(samples) * ratio)
        resampled = array.array('h', [0]) * new_len
        for i in range(new_len):
            src = int(i / ratio)
            if src < len(samples): resampled[i] = samples[src]
        samples = resampled

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


# ── reCAPTCHA Token ────────────────────────────────────────────

def _load_env() -> dict:
    """Load .env file from playwright-termux directory."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            if '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def get_token_playwright() -> Tuple[Optional[str], Optional[str]]:
    """
    Get reCAPTCHA v3 token via Playwright + Chromium.
    
    Launches headless Chromium, navigates to Muxlisa, injects the
    reCAPTCHA API, executes grecaptcha.execute(), and returns the token.
    
    Returns: (token, error_message)
    """
    env = _load_env()
    chromium_path = env.get("CHROMIUM_PATH") or os.environ.get("CHROMIUM_PATH") or CHROMIUM_DEFAULT

    if not os.path.exists(chromium_path):
        return None, f"Chromium not found at {chromium_path}"
    if not TOKEN_SCRIPT.exists():
        return None, f"get_token.js not found at {TOKEN_SCRIPT}"

    result = subprocess.run(
        ["node", str(TOKEN_SCRIPT)],
        capture_output=True, text=True, timeout=90,
        cwd=str(PW_DIR),
        env={**os.environ,
             "PLAYWRIGHT_BROWSERS_PATH": "0",
             "CHROMIUM_PATH": chromium_path}
    )

    if result.returncode != 0:
        return None, result.stderr.strip()[:300]
    return result.stdout.strip(), None


def get_token_capsolver(api_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get reCAPTCHA v3 token via Capsolver API.
    
    Capsolver uses real browsers to solve captchas, achieving scores
    of 0.7-0.9 (vs Playwright's 0.3). Free $1 credit on signup.
    
    Returns: (token, error_message)
    """
    payload = {
        "clientKey": api_key,
        "task": {
            "type": "ReCaptchaV3TaskProxyless",
            "websiteURL": PAGE_URL,
            "websiteKey": RECAPTCHA_SITE_KEY,
            "pageAction": "enquiryFormSubmit",
        }
    }
    try:
        r = requests.post("https://api.capsolver.com/createTask", json=payload, timeout=15).json()
    except Exception as e:
        return None, f"Capsolver connection error: {e}"

    if r.get("errorId") != 0:
        return None, r.get("errorDescription", str(r))

    task_id = r["taskId"]
    for _ in range(60):
        time.sleep(3)
        try:
            r = requests.post("https://api.capsolver.com/getTaskResult",
                            json={"clientKey": api_key, "taskId": task_id}, timeout=15).json()
        except Exception as e:
            return None, f"Capsolver poll error: {e}"

        if r.get("status") == "ready":
            return r["solution"]["gRecaptchaResponse"], None
        if r.get("status") == "failed":
            return None, f"Capsolver: {r.get('errorDescription', 'task failed')}"

    return None, "Capsolver timeout"


def get_token() -> Tuple[Optional[str], Optional[str]]:
    """
    Get a reCAPTCHA v3 token using the best available method.
    
    Priority:
      1. CAPSOLVER_API_KEY env var -> Capsolver API (score: 0.7-0.9)
      2. Playwright + Chromium     -> local browser (score: 0.3-0.5)
    """
    capsolver_key = os.environ.get("CAPSOLVER_API_KEY")
    if capsolver_key:
        return get_token_capsolver(capsolver_key)
    return get_token_playwright()


# ── Main API Call ──────────────────────────────────────────────

def transcribe(audio_path: str, recaptcha_token: Optional[str] = None,
               dry_run: bool = False, verbose: bool = True) -> dict:
    """
    Transcribe audio file using Muxlisa free demo API.
    
    Args:
        audio_path: Path to WAV audio file (max ~10 seconds)
        recaptcha_token: reCAPTCHA v3 token (auto-fetched if None)
        dry_run: Compute Unique-Key only, don't call API
        verbose: Print progress to stderr
    
    Returns:
        dict with keys: status_code, transcript (on success), error (on failure)
    """
    def log(msg):
        if verbose: print(msg, file=sys.stderr)

    # Validate input
    if not os.path.exists(audio_path):
        return {"error": f"File not found: {audio_path}", "status_code": 400}

    # Get reCAPTCHA token
    if not recaptcha_token and not dry_run:
        token, err = get_token()
        if err:
            return {"error": f"reCAPTCHA failed: {err}", "status_code": 400}
        recaptcha_token = token
        log(f"✅ Token: {recaptcha_token[:30]}...")

    # Convert audio + generate filename (timestamped like frontend)
    ts = int(time.time() * 1000)
    filename = f"{ts}.wav"
    wav_bytes = convert_audio(audio_path, max_sec=10)
    unique_key = compute_unique_key(filename)
    log(f"🔑 Key: {unique_key} ({len(wav_bytes)//32000}s audio)")

    if dry_run:
        return {"status": "dry_run", "unique_key": unique_key, "filename": filename}

    # Call the API
    files = {"file": (filename, io.BytesIO(wav_bytes), "audio/wav")}
    form = {"g-recaptcha-v3": recaptcha_token, "g-recaptcha-v2": ""}
    headers = {"Unique-Key": unique_key, "Access-Control-Allow-Origin": "*"}

    try:
        log("📤 Sending...")
        resp = requests.post(DEMO_ENDPOINT, headers=headers, data=form, files=files, timeout=60)
    except requests.exceptions.Timeout:
        return {"error": "API timeout", "status_code": 504}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection error: {e}", "status_code": 502}

    # Parse response
    try:
        result = resp.json()
    except Exception:
        result = {"raw": resp.text[:500]}

    result["status_code"] = resp.status_code

    if resp.status_code == 200:
        transcript = None
        if isinstance(result.get("result"), dict):
            transcript = result["result"].get("text")
        elif result.get("detail"):
            transcript = result["detail"]
        result["transcript"] = transcript
        log(f"📝 {transcript}" if transcript else "⚠ No transcript in response")
    else:
        log(f"❌ {resp.status_code}: {result.get('error', resp.text[:200])}")

    return result


# ── CLI ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Muxlisa STT Demo — Transcribe Uzbek speech to text")
    parser.add_argument("audio_file", help="Path to WAV audio file")
    parser.add_argument("--token", help="reCAPTCHA v3 token (skip auto-fetch)")
    parser.add_argument("--dry-run", action="store_true", help="Only compute Unique-Key")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    result = transcribe(args.audio_file, args.token, args.dry_run, verbose=not args.quiet)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)
    elif result.get("transcript"):
        print(result["transcript"])
    elif result.get("status") == "dry_run":
        print(f"Unique-Key: {result['unique_key']}")
