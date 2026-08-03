#!/usr/bin/env python3
"""
Muxlisa STT Demo — Core Engine

Transcribes Uzbek speech to text using Muxlisa.uz's free demo API.
Handles reCAPTCHA token generation (Playwright or Capsolver), Unique-Key
computation (reverse-engineered from frontend JS), and audio conversion.

Supports audio of ANY length by splitting at silence boundaries into
~10-second chunks, transcribing each, and merging the results.

Usage:
  python3 transcribe.py audio.wav                        # auto (Playwright)
  CAPSOLVER_API_KEY="key" python3 transcribe.py audio.wav # higher score
  python3 transcribe.py audio.wav --token TOKEN           # manual token
"""

import hashlib, io, json, math, os, subprocess, sys, tempfile, time, array
from pathlib import Path
from typing import Optional, Tuple, List

import requests

# ── Constants (from reverse-engineering the frontend) ──────────

DEMO_SALT = "b01b6852888f401689483814d4e1e6e0f68"
DEMO_ENDPOINT = "https://api.muxlisa.uz/v1/api/services/stt-demo/"
RECAPTCHA_SITE_KEY = "6LfrVHopAAAAALEkxrmPZsw1vRpAvcc8f1nn7EcY"
PAGE_URL = "https://muxlisa.uz/en"
MAX_CHUNK_SEC = 10  # demo limit

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

def load_audio(path: str, target_sr: int = 16000) -> Tuple[array.array, int]:
    """
    Load any audio file as mono 16-bit PCM at target_sr.
    Returns (samples_array, sample_rate).
    Supports WAV, MP3, FLAC, OGG, M4A via ffmpeg.
    """
    ext = Path(path).suffix.lower()

    # For WAV, try direct read first (fast path)
    if ext == '.wav':
        try:
            import wave
            with wave.open(path, 'rb') as w:
                ch, sw, fr, nf = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
                raw = w.readframes(nf)
            if raw and sw in (1, 2):
                if sw == 1:
                    s = array.array('h', (int((b - 128) * 256) for b in raw[::ch]))
                else:
                    arr = array.array('h'); arr.frombytes(raw[:nf * ch * 2])
                    s = array.array('h', (arr[i] for i in range(0, len(arr), ch)))
                # Resample if needed
                if fr != target_sr:
                    ratio = target_sr / fr
                    new_len = int(len(s) * ratio)
                    rs = array.array('h', [0]) * new_len
                    for i in range(new_len):
                        src = int(i / ratio)
                        if src < len(s): rs[i] = s[src]
                    s = rs
                return s, target_sr
        except Exception:
            pass  # fall through to ffmpeg

    # Use ffmpeg for all formats (WAV fallback + non-WAV)
    import subprocess, struct
    cmd = ['ffmpeg', '-i', path, '-f', 's16le', '-acodec', 'pcm_s16le',
           '-ac', '1', '-ar', str(target_sr), '-vn', '-loglevel', 'error', '-']
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg error: {proc.stderr.decode(errors='replace')[:200]}")
        raw = proc.stdout
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg (pkg install ffmpeg / apt install ffmpeg)")

    s = array.array('h')
    s.frombytes(raw)
    return s, target_sr


def audio_to_wav_bytes(samples: array.array, sr: int = 16000) -> bytes:
    """Convert samples array to WAV bytes."""
    import wave
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def find_split_points(samples: array.array, sr: int, max_chunk: int = MAX_CHUNK_SEC) -> List[int]:
    """
    Find optimal split points near max_chunk boundaries.
    Looks for silence (low energy) closest to each boundary so speech
    is never cut mid-word.
    """
    if len(samples) / sr <= max_chunk:
        return []

    chunk_frames = max_chunk * sr
    total_frames = len(samples)
    splits = []
    search_window = int(0.3 * sr)  # look 300ms around boundary

    # Compute per-frame energy (rectified)
    # Use windowed RMS for smoother detection
    window = int(0.05 * sr)  # 50ms window
    rms = array.array('f', [0.0]) * (total_frames // window + 1)
    for i in range(0, total_frames, window):
        chunk = samples[i:i + window]
        if len(chunk) == 0: break
        sq = sum((int(s) ** 2) for s in chunk) / len(chunk)
        rms[i // window] = math.sqrt(sq)

    # Find noise floor (10th percentile)
    sorted_rms = sorted(rms)
    noise_floor = sorted_rms[max(0, int(len(sorted_rms) * 0.05))]
    threshold = noise_floor * 3  # silence = below 3x noise floor

    pos = chunk_frames
    while pos < total_frames:
        start_search = max(0, pos - search_window)
        end_search = min(total_frames - 1, pos + search_window)

        best_split = pos
        best_energy = float('inf')

        for f in range(start_search, end_search):
            idx = f // window
            if idx < len(rms):
                e = rms[idx]
                if e < best_energy:
                    best_energy = e
                    best_split = f

        # Only split at silence points; otherwise split at exact boundary
        if best_energy > threshold:
            best_split = pos  # no silence found, cut at boundary

        splits.append(best_split)
        pos = best_split + chunk_frames

    return splits


def split_audio(samples: array.array, sr: int, splits: List[int]) -> List[Tuple[int, int]]:
    """Return list of (start_frame, end_frame) for each chunk."""
    chunks = []
    start = 0
    for sp in splits:
        chunks.append((start, sp))
        start = sp
    if start < len(samples):
        chunks.append((start, len(samples)))
    return chunks


def convert_audio(path: str, max_sec: int = MAX_CHUNK_SEC) -> bytes:
    """
    Load audio, convert to 16-bit mono 16kHz, and return WAV bytes.
    If shorter than max_sec, returns full file. If longer, use split_and_transcribe.
    (kept for backward compatibility)
    """
    samples, sr = load_audio(path)
    duration = len(samples) / sr
    if duration > max_sec:
        # Truncate
        n = int(sr * max_sec)
        samples = samples[:n]
    return audio_to_wav_bytes(samples, sr)


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


def get_token_nocaptcha(api_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get reCAPTCHA v3 token via NoCaptchaAI.
    
    Free tier: 200 solves/day (6,000/month). Scores 0.7-0.9.
    Sign up at https://nocaptchaai.com
    """
    payload = {
        "clientKey": api_key,
        "task": {
            "type": "ReCaptchaV3TaskProxyLess",
            "websiteURL": PAGE_URL,
            "websiteKey": RECAPTCHA_SITE_KEY,
            "pageAction": "enquiryFormSubmit",
        }
    }
    try:
        r = requests.post("https://api.nocaptchaai.com/createTask", json=payload, timeout=20).json()
    except Exception as e:
        return None, f"NoCaptchaAI connection error: {e}"

    if r.get("errorId") != 0:
        return None, r.get("errorDescription") or r.get("errorCode", str(r))

    task_id = r["taskId"]
    for _ in range(60):
        time.sleep(2)
        try:
            r = requests.post("https://api.nocaptchaai.com/getTaskResult",
                            json={"clientKey": api_key, "taskId": task_id}, timeout=15).json()
        except Exception as e:
            return None, f"NoCaptchaAI poll error: {e}"

        if r.get("status") == "ready":
            return r["solution"]["token"], None
        if r.get("status") == "failed":
            return None, f"NoCaptchaAI: {r.get('errorDescription', 'task failed')}"

    return None, "NoCaptchaAI timeout"


def get_token_nopecha(api_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get reCAPTCHA v3 token via Nopecha Token API.
    
    Free tier: 100 credits/day (5 reCAPTCHA v3 solves at 20 credits each).
    Simple REST API — submit, then poll for result.
    Sign up at https://nopecha.com
    """
    # Submit
    try:
        r = requests.post("https://api.nopecha.com/v1/token/recaptcha3", json={
            "key": api_key,
            "sitekey": RECAPTCHA_SITE_KEY,
            "url": PAGE_URL,
            "data": {"action": "enquiryFormSubmit"},
        }, timeout=20)
    except Exception as e:
        return None, f"Nopecha connection error: {e}"

    try:
        body = r.json()
    except Exception:
        return None, f"Nopecha bad response: {r.text[:200]}"

    if "error" in body:
        return None, f"Nopecha: {body['error']}"
    if "data" not in body:
        return None, f"Nopecha unexpected: {body}"

    job_id = body["data"]

    # Poll for result (Nopecha Token API takes ~30-60s)
    for _ in range(60):
        time.sleep(3)
        try:
            r = requests.get(
                f"https://api.nopecha.com/v1/token/recaptcha3",
                params={"key": api_key, "id": job_id},
                timeout=15,
            )
            body = r.json()
        except Exception as e:
            return None, f"Nopecha poll error: {e}"

        if "data" in body and body["data"]:
            token = body["data"]
            # Nopecha returns the token directly as a string
            if isinstance(token, str) and len(token) > 50:
                return token, None
            if isinstance(token, list) and token:
                return token[0], None
        if "error" in body:
            return None, f"Nopecha: {body['error']}"

    return None, "Nopecha timeout"


def get_token_captchaai(api_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get reCAPTCHA v3 token via CaptchaAI (2Captcha-style API).
    
    Paid service (from ~$15/mo) with free trial via support ticket.
    Uses in.php/res.php endpoints like 2Captcha.
    Sign up at https://captchaai.com
    """
    # Submit task
    try:
        r = requests.post("https://ocr.captchaai.com/in.php", data={
            "key": api_key,
            "method": "userrecaptcha",
            "version": "v3",
            "action": "enquiryFormSubmit",
            "googlekey": RECAPTCHA_SITE_KEY,
            "pageurl": PAGE_URL,
            "json": 1,
        }, timeout=20)
        body = r.json()
    except Exception as e:
        return None, f"CaptchaAI connection error: {e}"

    if body.get("status") != 1:
        return None, f"CaptchaAI: {body.get('request', body)}"

    task_id = body["request"]

    # Poll for result
    for _ in range(120):
        time.sleep(5)
        try:
            r = requests.get("https://ocr.captchaai.com/res.php", params={
                "key": api_key, "action": "get", "id": task_id, "json": 1,
            }, timeout=15)
            body = r.json()
        except Exception as e:
            return None, f"CaptchaAI poll error: {e}"

        if body.get("status") == 1:
            return body["request"], None
        if body.get("request") != "CAPCHA_NOT_READY":
            return None, f"CaptchaAI: {body.get('request', body)}"

    return None, "CaptchaAI timeout"


def get_token_2captcha(api_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get reCAPTCHA v3 token via 2Captcha.
    
    Classic paid solver (~$1-3/1000 solves). reCAPTCHA v3 supported
    with min_score parameter. Sign up at https://2captcha.com
    """
    try:
        r = requests.post("https://2captcha.com/in.php", data={
            "key": api_key,
            "method": "userrecaptcha",
            "version": "v3",
            "action": "enquiryFormSubmit",
            "min_score": 0.3,
            "googlekey": RECAPTCHA_SITE_KEY,
            "pageurl": PAGE_URL,
            "json": 1,
        }, timeout=20)
        body = r.json()
    except Exception as e:
        return None, f"2Captcha connection error: {e}"

    if body.get("status") != 1:
        return None, f"2Captcha: {body.get('request', body)}"

    task_id = body["request"]

    # Poll for result
    for _ in range(120):
        time.sleep(5)
        try:
            r = requests.get("https://2captcha.com/res.php", params={
                "key": api_key, "action": "get", "id": task_id, "json": 1,
            }, timeout=15)
            body = r.json()
        except Exception as e:
            return None, f"2Captcha poll error: {e}"

        if body.get("status") == 1:
            return body["request"], None
        if body.get("request") != "CAPCHA_NOT_READY":
            return None, f"2Captcha: {body.get('request', body)}"

    return None, "2Captcha timeout"


def get_token() -> Tuple[Optional[str], Optional[str]]:
    """
    Get a reCAPTCHA v3 token using the best available method.
    
    To force a specific provider, set CAPTCHA_PROVIDER env var:
      CAPTCHA_PROVIDER=nopecha | nocaptchaai | captchaai | capsolver | playwright
    
    Default priority (if CAPTCHA_PROVIDER unset):
      1. NOPECHA_API_KEY    -> Nopecha (5 free solves/day ✅)
      2. NOCAPTCHA_API_KEY  -> NoCaptchaAI (200 free solves/day)
      3. CAPTCHAAI_API_KEY  -> CaptchaAI (paid, ~$15/mo)
      4. CAPSOLVER_API_KEY  -> Capsolver API
      5. Playwright+Chromium -> local browser
    """
    providers = {
        "nopecha":     lambda k: get_token_nopecha(k),
        "nocaptchaai": lambda k: get_token_nocaptcha(k),
        "captchaai":   lambda k: get_token_captchaai(k),
        "capsolver":   lambda k: get_token_capsolver(k),
        "twocaptcha":  lambda k: get_token_2captcha(k),
        "playwright":  lambda k: get_token_playwright(),
    }
    keys = {
        "nopecha":     "NOPECHA_API_KEY",
        "nocaptchaai": "NOCAPTCHA_API_KEY",
        "captchaai":   "CAPTCHAAI_API_KEY",
        "capsolver":   "CAPSOLVER_API_KEY",
        "twocaptcha":  "TWOCAPTCHA_API_KEY",
        "playwright":  None,  # no key needed
    }

    forced = os.environ.get("CAPTCHA_PROVIDER", "").strip().lower()
    if forced:
        if forced not in providers:
            return None, f"Unknown CAPTCHA_PROVIDER: {forced} (choose from {', '.join(providers)})"
        if forced == "playwright":
            return get_token_playwright()
        key = os.environ.get(keys[forced])
        if not key:
            return None, f"CAPTCHA_PROVIDER={forced} but {keys[forced]} not set"
        return providers[forced](key)

    # Default priority
    nopecha_key = os.environ.get("NOPECHA_API_KEY")
    if nopecha_key:
        return get_token_nopecha(nopecha_key)
    nocaptcha_key = os.environ.get("NOCAPTCHA_API_KEY")
    if nocaptcha_key:
        return get_token_nocaptcha(nocaptcha_key)
    captchaai_key = os.environ.get("CAPTCHAAI_API_KEY")
    if captchaai_key:
        return get_token_captchaai(captchaai_key)
    capsolver_key = os.environ.get("CAPSOLVER_API_KEY")
    if capsolver_key:
        return get_token_capsolver(capsolver_key)
    return get_token_playwright()


# ── Main API Call ──────────────────────────────────────────────

def _transcribe_chunk(wav_bytes: bytes, recaptcha_token: str,
                       chunk_idx: int, total_chunks: int,
                       verbose: bool) -> Optional[str]:
    """Send a single audio chunk to the demo API and return transcript text."""
    def log(msg):
        if verbose: print(msg, file=sys.stderr)

    ts = int(time.time() * 1000)
    filename = f"chunk{chunk_idx}_{ts}.wav"
    unique_key = compute_unique_key(filename)

    files = {"file": (filename, io.BytesIO(wav_bytes), "audio/wav")}
    form = {"g-recaptcha-v3": recaptcha_token, "g-recaptcha-v2": ""}
    headers = {"Unique-Key": unique_key, "Access-Control-Allow-Origin": "*"}

    dur = len(wav_bytes) / 32000
    tag = f"[{chunk_idx + 1}/{total_chunks}]" if total_chunks > 1 else ""
    log(f"  {tag} sending chunk ({dur:.1f}s)...")

    try:
        resp = requests.post(DEMO_ENDPOINT, headers=headers, data=form,
                           files=files, timeout=60)
    except Exception as e:
        log(f"  {tag} ❌ request failed: {e}")
        return None

    if resp.status_code == 200:
        try:
            data = resp.json()
            text = None
            if isinstance(data.get("result"), dict):
                text = data["result"].get("text")
            elif data.get("detail"):
                text = data["detail"]
            if text:
                log(f"  {tag} ✅ got {len(text)} chars")
                return text
        except Exception:
            pass

    log(f"  {tag} ❌ {resp.status_code}: {resp.text[:100]}")
    return None


def transcribe(audio_path: str, recaptcha_token: Optional[str] = None,
               dry_run: bool = False, verbose: bool = True) -> dict:
    """
    Transcribe audio file using Muxlisa free demo API.
    
    Automatically splits audio longer than ~10s into chunks at silence
    boundaries, transcribes each chunk, and merges the results.
    
    Args:
        audio_path: Path to audio file (WAV, MP3, FLAC, OGG, M4A)
        recaptcha_token: reCAPTCHA v3 token (auto-fetched if None)
        dry_run: Compute Unique-Key only, don't call API
        verbose: Print progress to stderr
    
    Returns:
        dict with keys: status_code, transcript (on success), 
                        chunks (list of per-chunk results), error
    """
    def log(msg):
        if verbose: print(msg, file=sys.stderr)

    if not os.path.exists(audio_path):
        return {"error": f"File not found: {audio_path}", "status_code": 400}

    # Load audio
    samples, sr = load_audio(audio_path)
    duration = len(samples) / sr
    log(f"🎵 Loaded: {Path(audio_path).name} ({duration:.1f}s, {sr}Hz)")

    if dry_run:
        splits = find_split_points(samples, sr)
        chunks = split_audio(samples, sr, splits)
        return {
            "status": "dry_run",
            "duration_sec": duration,
            "num_chunks": len(chunks),
            "chunks": [{"start": f"{s/sr:.1f}s", "end": f"{e/sr:.1f}s",
                        "len_sec": round((e - s) / sr, 1)}
                       for s, e in chunks],
        }

    # Get reCAPTCHA token (reused for all chunks to save time)
    if not recaptcha_token:
        token, err = get_token()
        if err:
            return {"error": f"reCAPTCHA failed: {err}", "status_code": 400}
        recaptcha_token = token
        log(f"✅ Token: {recaptcha_token[:30]}...")

    # Find split points and create chunks
    splits = find_split_points(samples, sr)
    chunk_ranges = split_audio(samples, sr, splits)
    num_chunks = len(chunk_ranges)

    if num_chunks == 1:
        log(f"📤 Sending ({duration:.1f}s)...")
        wav = audio_to_wav_bytes(samples, sr)
        text = _transcribe_chunk(wav, recaptcha_token, 0, 1, verbose)
        if text:
            return {"status_code": 200, "transcript": text,
                    "duration_sec": duration, "chunks": [text]}
        return {"status_code": 502, "error": "Transcription failed"}

    log(f"✂️ Splitting into {num_chunks} chunks at silence boundaries...")
    if verbose:
        for i, (s, e) in enumerate(chunk_ranges):
            print(f"     chunk {i+1}: {s/sr:.1f}s → {e/sr:.1f}s ({(e-s)/sr:.1f}s)", file=sys.stderr)

    # Transcribe each chunk
    texts = []
    for i, (start, end) in enumerate(chunk_ranges):
        chunk_samples = samples[start:end]
        wav = audio_to_wav_bytes(chunk_samples, sr)
        text = _transcribe_chunk(wav, recaptcha_token, i, num_chunks, verbose)
        if text:
            texts.append(text)
        else:
            texts.append("[error]")

    merged = " ".join(t for t in texts if t and t != "[error]").strip()
    log(f"\n📝 Merged ({len(merged)} chars)")

    return {
        "status_code": 200 if merged else 502,
        "transcript": merged or None,
        "duration_sec": duration,
        "chunks": texts,
        "num_chunks": num_chunks,
    }


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
        dur = result.get("duration_sec", 0)
        n = result.get("num_chunks", 0)
        print(f"Duration: {dur:.1f}s → {n} chunk(s)")
        for c in result.get("chunks", []):
            print(f"  {c['start']} → {c['end']}  ({c['len_sec']}s)")
