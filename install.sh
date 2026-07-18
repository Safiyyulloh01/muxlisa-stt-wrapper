#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# Muxlisa STT Wrapper — Installer
# Detects platform (Termux/Android vs Linux), installs deps,
# sets up .env, and creates the working environment.
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
info()  { echo -e "  ${CYAN}→${NC} $1"; }
ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
err()   { echo -e "  ${RED}✗${NC} $1"; }
header() { echo -e "\n${BOLD}$1${NC}"; echo -e "${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ── Spinner for long-running commands ───────────────────────

spin() {
  local pid=$1 msg="$2"
  local chars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local i=0
  echo -n "  ${CYAN}${chars:i++%${#chars}:1}${NC} $msg "
  while kill -0 "$pid" 2>/dev/null; do
    echo -ne "\r  ${CYAN}${chars:i++%${#chars}:1}${NC} $msg "
    sleep 0.1
  done
  wait "$pid" 2>/dev/null
  if [[ $? -eq 0 ]]; then
    echo -e "\r  ${GREEN}✓${NC} $msg "
  else
    echo -e "\r  ${RED}✗${NC} $msg "
    return 1
  fi
}

run_spin() {
  local msg="$1"; shift
  ("$@" &>/dev/null) &
  local pid=$!
  spin "$pid" "$msg"
  return $?
}

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
  header "System Dependencies"
  if $IS_TERMUX; then
    run_spin "Updating package lists..." pkg update -y
    run_spin "Installing python, nodejs..." pkg install -y python nodejs
    run_spin "Installing chromium..." pkg install -y chromium
    run_spin "Installing ffmpeg..." pkg install -y ffmpeg
  elif $IS_LINUX; then
    if command -v apt &>/dev/null; then
      run_spin "Updating package lists..." sudo apt update -y
      run_spin "Installing python3, nodejs..." sudo apt install -y python3 python3-pip python3-venv nodejs
      run_spin "Installing chromium..." sudo apt install -y chromium-browser chromium 2>/dev/null
      run_spin "Installing ffmpeg..." sudo apt install -y ffmpeg
    elif command -v pacman &>/dev/null; then
      run_spin "Installing packages..." sudo pacman -Sy --noconfirm python python-pip nodejs chromium ffmpeg
    elif command -v dnf &>/dev/null; then
      run_spin "Installing python3, nodejs..." sudo dnf install -y python3 python3-pip nodejs
      run_spin "Installing chromium..." sudo dnf install -y chromium
      run_spin "Installing ffmpeg..." sudo dnf install -y ffmpeg
    else
      warn "Unknown package manager. Install python3, nodejs, chromium, ffmpeg manually."
    fi
  fi
}

# ── Install Python deps ────────────────────────────────────────

install_python_deps() {
  header "Python Dependencies"
  run_spin "Installing Python packages (fastapi, uvicorn, requests)..." \
    pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt
}

# ── Install Node deps ──────────────────────────────────────────

install_node_deps() {
  header "Node.js Dependencies"
  cd "$SCRIPT_DIR/playwright-termux"
  if $IS_TERMUX; then
    run_spin "Installing playwright-core (Termux-compatible)..." npm install playwright-core@1.54.1 dotenv
  else
    run_spin "Installing playwright..." npm install playwright dotenv
  fi
  cd "$SCRIPT_DIR"
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

  echo "  ${DIM}--- playwright-termux/.env ---${NC}"
  while IFS= read -r line; do
    if [[ -n "$line" && ! "$line" =~ ^# ]]; then
      echo "    $line"
    fi
  done < "$SCRIPT_DIR/playwright-termux/.env" 2>/dev/null
  echo
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
