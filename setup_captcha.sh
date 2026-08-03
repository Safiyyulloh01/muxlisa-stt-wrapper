#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Captcha Solver Provider Setup — Interactive Menu
#
# ↑/↓ arrow keys to navigate, description panel updates live.
# Enter to select provider → enter API key → Enter confirms,
# Esc/Back returns to the menu without saving.
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/playwright-termux/.env"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
RED='\033[0;31m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
REV='\033[7m'

# ── Provider definitions: name|env_var|provider_id|description|signup_url|cost ──

PROVIDERS=(
  "Nopecha|NOPECHA_API_KEY|nopecha|Free: 100 credits/day = 5 reCAPTCHA v3 solves daily. Sign in with GitHub and click 'Free GitHub Key'.|https://nopecha.com/manage|FREE"
  "NoCaptchaAI|NOCAPTCHA_API_KEY|nocaptchaai|AI-powered solver, claims 200 free solves/day. Sign up at nocaptchaai.com. May need plan activation in dashboard.|https://nocaptchaai.com|FREE"
  "Capsolver|CAPSOLVER_API_KEY|capsolver|Reliable paid solver, scores 0.7-0.9, ~\$0.002/solve. No free tier.|https://capsolver.com|PAID"
  "CaptchaAI|CAPTCHAAI_API_KEY|captchaai|Paid solver from ~\$15/mo, 2Captcha-compatible in.php/res.php API. Free trial via support ticket.|https://captchaai.com|PAID"
  "2Captcha|TWOCAPTCHA_API_KEY|twocaptcha|Classic paid solver, ~\$1-3/1000 solves. Supports reCAPTCHA v3 with min_score parameter.|https://2captcha.com|PAID"
  "Playwright|NONE|playwright|Local Chromium browser, no key needed. Scores ~0.3 on Termux, 0.5+ on Linux. Automatic fallback when no key set.|local browser|FREE"
)

NUM_PROVIDERS=${#PROVIDERS[@]}

# ── Terminal helpers ───────────────────────────────────────────

hide_cursor() { printf '\033[?25l'; }
show_cursor() { printf '\033[?25h'; }
clear_screen() { printf '\033[2J\033[H'; }

# ── Render main menu ───────────────────────────────────────────

render_menu() {
  local sel=$1
  clear_screen

  printf "${BOLD}${CYAN}┌────────────────────────────────────────────────────────────┐${NC}\n"
  printf "${BOLD}${CYAN}│        Captcha Solver Provider Setup                      │${NC}\n"
  printf "${BOLD}${CYAN}│   ↑/↓ navigate   Enter select   q quit                    │${NC}\n"
  printf "${BOLD}${CYAN}└────────────────────────────────────────────────────────────┘${NC}\n\n"

  # Provider list
  for i in "${!PROVIDERS[@]}"; do
    IFS='|' read -r name env_var provider_id desc url cost <<< "${PROVIDERS[$i]}"
    local marker
    if [[ -f "$ENV_FILE" ]] && grep -q "^${env_var}=" "$ENV_FILE" 2>/dev/null; then
      marker="${GREEN}●${NC}"  # configured
    else
      marker="${DIM}○${NC}"
    fi

    if [[ $i -eq $sel ]]; then
      printf "  ${REV}${GREEN}▶${NC}${REV} ${name} ${NC} ${marker}  ${DIM}${env_var}${NC}\n"
    else
      printf "    ${name} ${marker}  ${DIM}${env_var}${NC}\n"
    fi
  done

  # Description panel
  IFS='|' read -r name env_var provider_id desc url cost <<< "${PROVIDERS[$sel]}"
  printf "\n${DIM}┌────────────────────────────────────────────────────────────┐${NC}\n"
  printf "${DIM}│${NC} ${BOLD}${name}${NC}\n"
  printf "${DIM}│${NC} ${desc}\n"
  printf "${DIM}│${NC} ${BOLD}Sign up:${NC} ${CYAN}${url}${NC}\n"
  printf "${DIM}│${NC} ${BOLD}Cost:${NC} "
  if [[ "$cost" == "FREE" ]]; then
    printf "${GREEN}Free${NC}\n"
  else
    printf "${YELLOW}Paid${NC}\n"
  fi
  printf "${DIM}└────────────────────────────────────────────────────────────┘${NC}\n"
}

# ── Key entry screen ───────────────────────────────────────────

read_api_key() {
  local name=$1 env_var=$2
  local key=""

  clear_screen
  printf "${BOLD}${CYAN}┌────────────────────────────────────────────────────────────┐${NC}\n"
  printf "${BOLD}${CYAN}│        Enter API Key — ${name}${NC}\n"
  printf "${BOLD}${CYAN}└────────────────────────────────────────────────────────────┘${NC}\n\n"
  printf "  ${BOLD}${env_var}${NC}\n\n"
  printf "  ${DIM}Type your key, press Enter to confirm.${NC}\n"
  printf "  ${DIM}Esc = cancel and go back${NC}\n\n"

  while true; do
    printf "  ${GREEN}>${NC} "
    IFS= read -r key

    if [[ -n "$key" ]]; then
      printf "\n  ${YELLOW}Save this key?${NC}\n  ${BOLD}${key}${NC}\n\n"
      printf "  ${DIM}(Enter) confirm    (Esc) re-enter    (b) back to menu${NC}\n  "

      while true; do
        IFS= read -rsn1 choice
        if [[ "$choice" == $'\e' ]]; then
          # Esc — check if it's just Esc or arrow key
          read -rsn2 -t 0.05 esc_seq 2>/dev/null || true
          if [[ -z "$esc_seq" ]]; then
            return 1  # plain Esc → re-enter
          fi
          return 1
        elif [[ "$choice" == "" || "$choice" == $'\r' || "$choice" == $'\n' ]]; then
          printf "\n"
          save_key "$env_var" "$key" "$provider_id"
          printf "\n  ${GREEN}✓ Key saved for ${name}${NC}\n"
          printf "  ${DIM}Set as default provider (CAPTCHA_PROVIDER)${NC}\n"
          sleep 1
          return 0  # confirmed & saved
        elif [[ "$choice" == "b" || "$choice" == "B" ]]; then
          return 2  # back to menu
        fi
      done
    fi
  done
}

# ── Save key to .env ───────────────────────────────────────────

save_key() {
  local env_var=$1 key=$2 provider=$3
  mkdir -p "$(dirname "$ENV_FILE")"

  if [[ -f "$ENV_FILE" ]]; then
    grep -v "^${env_var}=\|^CAPTCHA_PROVIDER=" "$ENV_FILE" > "$ENV_FILE.tmp" 2>/dev/null || true
    mv "$ENV_FILE.tmp" "$ENV_FILE"
  fi

  echo "${env_var}=${key}" >> "$ENV_FILE"
  echo "CAPTCHA_PROVIDER=${provider}" >> "$ENV_FILE"
}

# ── Main loop ──────────────────────────────────────────────────

main_menu() {
  local sel=0
  local running=1

  hide_cursor
  trap 'show_cursor' EXIT

  while [[ $running -eq 1 ]]; do
    render_menu "$sel"

    IFS= read -rsn1 key
    if [[ "$key" == $'\e' ]]; then
      IFS= read -rsn2 -t 0.1 key2
      case "$key2" in
        '[A') ((sel--)); [[ $sel -lt 0 ]] && sel=$((NUM_PROVIDERS - 1)) ;;
        '[B') ((sel++)); [[ $sel -ge $NUM_PROVIDERS ]] && sel=0 ;;
      esac
    elif [[ "$key" == "" || "$key" == $'\r' || "$key" == $'\n' ]]; then
      IFS='|' read -r name env_var provider_id desc url cost <<< "${PROVIDERS[$sel]}"

      if [[ "$env_var" == "NONE" ]]; then
        # Playwright — no key needed
        clear_screen
        printf "${GREEN}✓${NC} Playwright selected — no API key needed.\n"
        printf "   Uses local Chromium for reCAPTCHA generation.\n\n"
        printf "  ${DIM}(Enter) set as default   (Esc) back${NC}\n  "
        while true; do
          IFS= read -rsn1 c
          [[ "$c" == $'\e' ]] && break
          [[ "$c" == "" || "$c" == $'\r' || "$c" == $'\n' ]] && {
            # Set Playwright as default provider
            mkdir -p "$(dirname "$ENV_FILE")"
            if [[ -f "$ENV_FILE" ]]; then
              grep -v "^CAPTCHA_PROVIDER=" "$ENV_FILE" > "$ENV_FILE.tmp" 2>/dev/null || true
              mv "$ENV_FILE.tmp" "$ENV_FILE"
            fi
            echo "CAPTCHA_PROVIDER=playwright" >> "$ENV_FILE"
            printf "\n  ${GREEN}✓ Playwright set as default provider${NC}\n"
            sleep 1
            running=0; break
          }
        done
        continue
      fi

      local result
      read_api_key "$name" "$env_var"
      result=$?
      if [[ $result -eq 0 ]]; then
        running=0  # saved, exit
      fi
      # result 1 (re-enter) and 2 (back) → loop continues
    elif [[ "$key" == "q" || "$key" == "Q" ]]; then
      running=0
    fi
  done

  show_cursor
}

main_menu
