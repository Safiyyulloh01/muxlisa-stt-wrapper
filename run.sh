#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# Muxlisa STT Wrapper — Run Script
# Starts the API service and handles environment setup.
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${CYAN}→${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; }

# ── Source .env ────────────────────────────────────────────────

ENV_FILE="$SCRIPT_DIR/playwright-termux/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
  info "Loaded .env"
fi

# ── Check dependencies ────────────────────────────────────────

check_dep() {
  if ! command -v "$1" &>/dev/null; then
    err "$1 not found. Run ./install.sh first."
    return 1
  fi
}

check_dep python3 || exit 1
check_dep node || exit 1

# ── Detect Chromium ────────────────────────────────────────────

CHROMIUM="${CHROMIUM_PATH:-}"
if [[ -z "$CHROMIUM" ]]; then
  for candidate in chromium-browser chromium google-chrome; do
    if command -v "$candidate" &>/dev/null; then
      CHROMIUM=$(command -v "$candidate")
      break
    fi
  done
fi

if [[ -n "$CHROMIUM" ]]; then
  ok "Chromium: $CHROMIUM"
  export CHROMIUM_PATH="$CHROMIUM"
else
  warn "No Chromium found — Playwright reCAPTCHA won't work"
  warn "Set CHROMIUM_PATH in playwright-termux/.env or install Capsolver"
fi

# ── Check Capsolver ───────────────────────────────────────────

if [[ -n "${CAPSOLVER_API_KEY:-}" ]]; then
  ok "Capsolver: configured"
fi

# ── Install Python deps if missing ────────────────────────────

if ! python3 -c "import fastapi" 2>/dev/null; then
  info "Installing Python dependencies..."
  pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt
fi

# ── Start service ──────────────────────────────────────────────

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║      Muxlisa STT API Service                ║${NC}"
echo -e "${GREEN}║──────────────────────────────────────────────║${NC}"
echo -e "${GREEN}║  Server:  http://$HOST:$PORT                    ║${NC}"
echo -e "${GREEN}║  Docs:    http://$HOST:$PORT/docs               ║${NC}"
echo -e "${GREEN}║  Status:  http://$HOST:$PORT/v1/health         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# Start server (keeps it in foreground for Ctrl+C to work)
exec python3 service.py --port "$PORT" 2>&1
