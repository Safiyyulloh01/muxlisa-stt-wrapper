#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# Muxlisa STT Wrapper — Installer
# Detects platform (Termux/Android vs Linux), installs deps,
# sets up .env, and creates the working environment.
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${CYAN}→${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; }

# ── Detect platform ────────────────────────────────────────────

IS_TERMUX=false
IS_LINUX=false

if [[ "$(uname -o 2>/dev/null)" == "Android" ]] || [[ -d /data/data/com.termux ]]; then
  IS_TERMUX=true
  info "Detected: Termux / Android"
elif [[ "$(uname -s)" == "Linux" ]]; then
  IS_LINUX=true
  info "Detected: Linux"
else
  warn "Unknown platform: $(uname -s) — proceeding with Linux defaults"
  IS_LINUX=true
fi

# ── Install system dependencies ────────────────────────────────

install_system_deps() {
  if $IS_TERMUX; then
    info "Installing Termux packages..."
    pkg update -y
    pkg install -y python nodejs chromium x11-repo 2>/dev/null || {
      warn "Some packages failed. Trying without x11-repo..."
      pkg install -y python nodejs chromium
    }
  elif $IS_LINUX; then
    if command -v apt &>/dev/null; then
      info "Installing Linux packages (apt)..."
      sudo apt update -y
      sudo apt install -y python3 python3-pip python3-venv nodejs chromium-browser || {
        sudo apt install -y python3 python3-pip nodejs chromium
      }
    elif command -v pacman &>/dev/null; then
      info "Installing Linux packages (pacman)..."
      sudo pacman -Sy --noconfirm python python-pip nodejs chromium
    elif command -v dnf &>/dev/null; then
      info "Installing Linux packages (dnf)..."
      sudo dnf install -y python3 python3-pip nodejs chromium
    else
      warn "Unknown package manager. Install python3, nodejs, chromium manually."
    fi
  fi
}

# ── Install Python deps ────────────────────────────────────────

install_python_deps() {
  info "Installing Python dependencies..."
  pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt
  ok "Python deps installed"
}

# ── Install Node deps ──────────────────────────────────────────

install_node_deps() {
  info "Installing Node.js dependencies..."
  cd "$SCRIPT_DIR/playwright-termux"
  
  if $IS_TERMUX; then
    npm install playwright-core@1.54.1 dotenv 2>/dev/null
  else
    npm install playwright dotenv 2>/dev/null
  fi
  
  cd "$SCRIPT_DIR"
  ok "Node.js deps installed"
}

# ── Setup .env ─────────────────────────────────────────────────

setup_env() {
  local env_file="$SCRIPT_DIR/playwright-termux/.env"
  
  if [[ -f "$env_file" ]] && grep -q "CHROMIUM_PATH" "$env_file" 2>/dev/null; then
    ok ".env already exists"
    return
  fi

  echo ""
  info "── .env Setup ──────────────────────────────"

  # Capsolver API key
  read -rp "Capsolver API key (press Enter to skip): " capsolver_key
  if [[ -n "$capsolver_key" ]]; then
    echo "CAPSOLVER_API_KEY=$capsolver_key" > "$env_file"
  fi

  # Chromium path
  local chromium_path=""
  if $IS_TERMUX; then
    chromium_path="/data/data/com.termux/files/usr/bin/chromium-browser"
  elif command -v chromium-browser &>/dev/null; then
    chromium_path=$(command -v chromium-browser)
  elif command -v chromium &>/dev/null; then
    chromium_path=$(command -v chromium)
  elif command -v google-chrome &>/dev/null; then
    chromium_path=$(command -v google-chrome)
  fi

  if [[ -n "$chromium_path" ]]; then
    echo "CHROMIUM_PATH=$chromium_path" >> "$env_file"
    ok "Chromium: $chromium_path"
  else
    warn "Chromium not found. Install manually or set CHROMIUM_PATH in .env"
    echo "# CHROMIUM_PATH=/path/to/chromium" >> "$env_file"
  fi

  echo "PLAYWRIGHT_BROWSERS_PATH=0" >> "$env_file"
  ok ".env created at $env_file"
}

# ── Verify ─────────────────────────────────────────────────────

verify() {
  echo ""
  info "── Verification ─────────────────────────────"
  
  python3 -c "import fastapi; print('FastAPI:', fastapi.__version__)" 2>/dev/null && ok "FastAPI OK" || warn "FastAPI not found"
  python3 -c "import requests; print('requests:', requests.__version__)" 2>/dev/null && ok "requests OK" || warn "requests not found"
  node -e "require('playwright-core')" 2>/dev/null && ok "playwright-core OK" || node -e "require('playwright')" 2>/dev/null && ok "playwright OK" || warn "playwright(-core) not found"

  if command -v chromium-browser &>/dev/null; then
    ok "chromium-browser: $(chromium-browser --version 2>/dev/null || true)"
  elif command -v chromium &>/dev/null; then
    ok "chromium: $(chromium --version 2>/dev/null || true)"
  else
    warn "No Chromium binary found"
  fi

  cat "$SCRIPT_DIR/playwright-termux/.env" 2>/dev/null | grep -v '^$' | grep -v '^#' | head -5
}

# ── Main ───────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       Muxlisa STT Wrapper - Installer       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""

install_system_deps
install_python_deps
install_node_deps
setup_env
verify

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Installation complete!                      ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  Start the API service:                      ║${NC}"
echo -e "${GREEN}║    ./run.sh                                   ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  Or transcribe a file directly:              ║${NC}"
echo -e "${GREEN}║    python3 transcribe.py speech.wav           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
