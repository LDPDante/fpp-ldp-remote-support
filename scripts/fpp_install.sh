#!/bin/bash
# Runs as ROOT after FPP clones the plugin. Do NOT use sudo. Idempotent.
set +e
export PATH="/usr/sbin:/sbin:/usr/bin:/bin:$PATH"
. ${FPPDIR}/scripts/common 2>/dev/null

PLUGIN_NAME="fpp-ldp-remote-support"
PLUGIN_DIR="/home/fpp/media/plugins/${PLUGIN_NAME}"
: "${LOGDIR:=/home/fpp/media/logs}"
LOG="${LOGDIR}/plugin-${PLUGIN_NAME}.log"
echo "$(date) fpp_install: starting" >> "$LOG"

# Ensure our scripts are executable regardless of how they arrived.
chmod +x "${PLUGIN_DIR}"/scripts/*.sh "${PLUGIN_DIR}"/commands/*.sh 2>/dev/null

# Prefer an internet-capable default route BEFORE downloading Tailscale, so the
# install works on a dual-homed controller (self-heals a dead prop-net gateway).
. "${PLUGIN_DIR}/scripts/ldp_lib.sh"
ldp_prefer_internet_route

# A fresh controller can boot with a bogus clock (no RTC / not yet NTP-synced),
# which breaks TLS to GitHub/Tailscale. Enable NTP and wait briefly for a sane year.
timedatectl set-ntp true 2>/dev/null
if [ "$(date -u +%Y)" -lt 2025 ] 2>/dev/null; then
  echo "$(date) fpp_install: clock looks wrong, waiting for NTP sync" >> "$LOG"
  for i in 1 2 3 4 5 6 7 8; do sleep 2; [ "$(date -u +%Y)" -ge 2025 ] 2>/dev/null && break; done
fi

# --- Install Tailscale (official installer auto-detects Pi/BeagleBone + OS) ---
if ! command -v tailscale >/dev/null 2>&1; then
  echo "$(date) fpp_install: installing tailscale" >> "$LOG"
  curl -fsSL https://tailscale.com/install.sh | sh >> "$LOG" 2>&1
fi
systemctl enable --now tailscaled >> "$LOG" 2>&1
# Let the FPP web user drive tailscale, so the customer's "Connect" button works
# (the web UI runs as 'fpp', not root).
tailscale set --operator=fpp >> "$LOG" 2>&1 || true

# --- Provisioning dir; make the key readable by the fpp web user so the
#     customer "Connect" button can enroll with it ---
install -d -m 0750 /etc/ldp
ldp_fix_key_perms

# --- Shipped default state (set at flash time; toggle stays user-selectable) ---
#   Sales units : OFF (opt-in) - the customer clicks "Connect to LDP Support".
#   Rental units: ON so they AUTO-CONNECT on power-up. Provision it before install:
#       echo True | sudo tee /etc/ldp/default_enabled
SETTINGS_FILE="/home/fpp/media/config/plugin.${PLUGIN_NAME}"
DEFAULT_ENABLED="False"
if [ -r /etc/ldp/default_enabled ]; then
  case "$(tr -d '[:space:]' < /etc/ldp/default_enabled | tr '[:upper:]' '[:lower:]')" in
    true|1|on|yes) DEFAULT_ENABLED="True" ;;
  esac
fi
if ! grep -q 'RemoteSupportEnabled' "$SETTINGS_FILE" 2>/dev/null; then
  echo "RemoteSupportEnabled = \"$DEFAULT_ENABLED\"" >> "$SETTINGS_FILE"
  chown fpp:fpp "$SETTINGS_FILE" 2>/dev/null
fi

# --- If enabled and a key has been provisioned, connect now ---
. "${PLUGIN_DIR}/scripts/ldp_lib.sh"
if ldp_enabled; then ldp_apply; fi

# Commands are only read at fppd startup -> ask for a restart.
setSetting restartFlag 1 2>/dev/null
echo "$(date) fpp_install: done" >> "$LOG"
exit 0
