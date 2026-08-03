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
  local pid=$1 msg=$2
  local chars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local i=0
  printf '  %s %s' "${CYAN}⠋${NC}" "$msg"
  while kill -0 "$pid" 2>/dev/null; do
    printf '\033[2K\r  %s %s' "${CYAN}${chars:i%${#chars}:1}${NC}" "$msg"
    i=$((i + 1))
    sleep 0.1
  done
  wait "$pid" 2>/dev/null
  local rc=$?
  if [[ $rc -eq 0 ]]; then
    printf '\033[2K\r  %s %s\n' "${GREEN}✓${NC}" "$msg"
  else
    printf '\033[2K\r  %s %s\n' "${RED}✗${NC}" "$msg"
  fi
  return $rc
}

run_spin() {
  local msg=$1; shift
  local logfile
  logfile=$(mktemp)
  "$@" >"$logfile" 2>&1 &
  local pid=$!
  spin "$pid" "$msg"
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo -e "  ${DIM}Error output:${NC}"
    tail -8 "$logfile" | sed 's/^/    /'
  fi
  rm -f "$logfile"
  return $rc
}

# ── Detect platform ────────────────────────────────────────────

IS_TERMUX=false
IS_LINUX=false

# Termux sets $PREFIX; also check uname and the well-known path
if [[ -n "${PREFIX:-}" ]] || [[ "$(uname -o 2>/dev/null)" == "Android" ]] || [[ -d /data/data/com.termux ]]; then
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

need_cmd() { ! command -v "$1" &>/dev/null; }

install_system_deps() {
  header "System Dependencies"
  if $IS_TERMUX; then
    local missing=()
    need_cmd python && missing+=(python)
    need_cmd node && missing+=(nodejs)
    need_cmd ffmpeg && missing+=(ffmpeg)
    # Chromium: Termux provides "chromium-browser", Linux usually "chromium".
    # Only report missing if NEITHER binary exists.
    if need_cmd chromium-browser && need_cmd chromium; then
      missing+=(chromium)
    fi

    if [[ ${#missing[@]} -eq 0 ]]; then
      ok "All system packages already installed (python, nodejs, chromium, ffmpeg)"
      return
    fi

    info "Missing: ${missing[*]}"
    # Fix broken package state first (common on Termux, e.g. ffmpeg post-install)
    run_spin "Upgrading existing packages (fixes broken state)..." pkg upgrade -y || warn "pkg upgrade failed, continuing..."
    # Chromium needs the x11-repo
    if need_cmd chromium-browser && need_cmd chromium; then
      run_spin "Enabling x11-repo (required for chromium)..." pkg install -y x11-repo || warn "x11-repo install failed"
    fi
    run_spin "Installing ${missing[*]}..." pkg install -y "${missing[@]}" || \
      warn "Some packages failed to install. Run manually: pkg install -y ${missing[*]}"
    local missing=()
    need_cmd python3 && missing+=(python3 python3-pip python3-venv)
    need_cmd node && missing+=(nodejs)
    need_cmd ffmpeg && missing+=(ffmpeg)
    if need_cmd chromium-browser && need_cmd chromium; then
      missing+=(chromium)
    fi

    if [[ ${#missing[@]} -eq 0 ]]; then
      ok "All system packages already installed (python3, nodejs, chromium, ffmpeg)"
      return
    fi

    info "Missing: ${missing[*]}"
    if command -v apt &>/dev/null; then
      run_spin "Updating package lists..." sudo apt update -y || warn "apt update failed, continuing..."
      run_spin "Installing ${missing[*]}..." sudo apt install -y "${missing[@]}" || \
        warn "Some packages failed. Run manually: sudo apt install -y ${missing[*]}"
    elif command -v pacman &>/dev/null; then
      run_spin "Installing ${missing[*]}..." sudo pacman -Sy --noconfirm "${missing[@]}" || \
        warn "Some packages failed. Run manually: sudo pacman -Sy --noconfirm ${missing[*]}"
    elif command -v dnf &>/dev/null; then
      run_spin "Installing ${missing[*]}..." sudo dnf install -y "${missing[@]}" || \
        warn "Some packages failed. Run manually: sudo dnf install -y ${missing[*]}"
    else
      warn "Unknown package manager. Install manually: ${missing[*]}"
    fi
  fi
}

# ── Install Python deps ────────────────────────────────────────

install_python_deps() {
  header "Python Dependencies"
  if python3 -c "import fastapi, requests, uvicorn" 2>/dev/null; then
    ok "Python deps already installed"
    return
  fi
  run_spin "Installing Python packages (fastapi, uvicorn, requests)..." \
    pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt || \
    warn "pip install failed. Run manually: pip install -r requirements.txt"
}

# ── Install Node deps ──────────────────────────────────────────

install_node_deps() {
  header "Node.js Dependencies"
  cd "$SCRIPT_DIR/playwright-termux"
  if [[ -d node_modules/playwright-core ]] || [[ -d node_modules/playwright ]]; then
    ok "Node deps already installed"
    cd "$SCRIPT_DIR"
    return
  fi
  if $IS_TERMUX; then
    run_spin "Installing playwright-core (Termux-compatible)..." npm install playwright-core@1.54.1 dotenv || \
      warn "npm install failed. Run manually in playwright-termux: npm install"
  else
    run_spin "Installing playwright..." npm install playwright dotenv || \
      warn "npm install failed. Run manually in playwright-termux: npm install"
  fi
  cd "$SCRIPT_DIR"
}

# ── Setup .env ─────────────────────────────────────────────────

setup_env() {
  local env_file="$SCRIPT_DIR/playwright-termux/.env"
  
  # Ensure .env dir exists with Chromium path
  mkdir -p "$SCRIPT_DIR/playwright-termux"

  # Detect Chromium path
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

  # Write base .env (preserving existing keys)
  local tmp_env="${env_file}.base"
  if [[ -f "$env_file" ]]; then
    cp "$env_file" "$tmp_env"
  else
    > "$tmp_env"
  fi
  grep -v "^CHROMIUM_PATH=\|^PLAYWRIGHT_BROWSERS_PATH=\|^PROFILE_DIR=\|^COOKIES_FILE=" "$tmp_env" > "${tmp_env}.2" 2>/dev/null || true
  mv "${tmp_env}.2" "$tmp_env"
  echo "PLAYWRIGHT_BROWSERS_PATH=0" >> "$tmp_env"
  echo "PROFILE_DIR=$HOME/.muxlisa-profile" >> "$tmp_env"
  echo "COOKIES_FILE=$HOME/.muxlisa-cookies.json" >> "$tmp_env"
  if [[ -n "$chromium_path" ]]; then
    echo "CHROMIUM_PATH=$chromium_path" >> "$tmp_env"
    ok "Chromium: $chromium_path"
  else
    warn "Chromium not found. Set CHROMIUM_PATH in .env"
  fi
  mv "$tmp_env" "$env_file"

  info "Browser profile: $HOME/.muxlisa-profile (persists cookies between runs)"
  info "Warm up the profile: cd playwright-termux && node warmup.js 5"

  # ── Interactive captcha solver selection ────────────────────
  # Skip if a solver key is already configured
  local has_solver=false
  for v in NOPECHA_API_KEY NOCAPTCHA_API_KEY CAPSOLVER_API_KEY CAPTCHAAI_API_KEY TWOCAPTCHA_API_KEY; do
    if grep -q "^${v}=" "$env_file" 2>/dev/null; then
      has_solver=true
      break
    fi
  done

  if [[ "$has_solver" == true ]]; then
    ok "Captcha solver already configured — skipping setup"
  elif [[ -t 0 ]]; then
    header "Captcha Solver Setup"
    info "Choose a provider (↑/↓ arrows, Enter to select)..."
    "$SCRIPT_DIR/setup_captcha.sh"
  else
    warn "Non-interactive shell — skipping captcha setup."
    info "Run ./setup_captcha.sh manually to configure a solver."
  fi
}

# ── Verify ─────────────────────────────────────────────────────

verify() {
  echo ""
  info "── Verification ─────────────────────────────"
  
  python3 -c "import fastapi; print('FastAPI:', fastapi.__version__)" 2>/dev/null && ok "FastAPI OK" || warn "FastAPI not found"
  python3 -c "import requests; print('requests:', requests.__version__)" 2>/dev/null && ok "requests OK" || warn "requests not found"
  # Check playwright from its own dir (node_modules lives there)
  if (cd "$SCRIPT_DIR/playwright-termux" && node -e "require('playwright-core')" 2>/dev/null) || \
     (cd "$SCRIPT_DIR/playwright-termux" && node -e "require('playwright')" 2>/dev/null); then
    ok "playwright(-core) OK"
  else
    warn "playwright(-core) not found — run: cd playwright-termux && npm install"
  fi

  if command -v chromium-browser &>/dev/null; then
    ok "chromium-browser: $(chromium-browser --version 2>/dev/null || true)"
  elif command -v chromium &>/dev/null; then
    ok "chromium: $(chromium --version 2>/dev/null || true)"
  else
    warn "No Chromium binary found"
  fi

  echo ""
  echo "  ${DIM}Services configured:${NC}"
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
echo -e "${GREEN}║  (use ./run.sh with the ./ prefix)           ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  Or transcribe a file directly:              ║${NC}"
echo -e "${GREEN}║    python3 transcribe.py speech.wav           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
