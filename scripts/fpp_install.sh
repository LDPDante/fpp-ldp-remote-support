#!/bin/bash
# Runs as ROOT after FPP clones the plugin. Do NOT use sudo. Idempotent.
set +e
. ${FPPDIR}/scripts/common 2>/dev/null

PLUGIN_NAME="fpp-ldp-remote-support"
PLUGIN_DIR="/home/fpp/media/plugins/${PLUGIN_NAME}"
: "${LOGDIR:=/home/fpp/media/logs}"
LOG="${LOGDIR}/plugin-${PLUGIN_NAME}.log"
echo "$(date) fpp_install: starting" >> "$LOG"

# Ensure our scripts are executable regardless of how they arrived.
chmod +x "${PLUGIN_DIR}"/scripts/*.sh "${PLUGIN_DIR}"/commands/*.sh 2>/dev/null

# --- Install Tailscale (official installer auto-detects Pi/BeagleBone + OS) ---
if ! command -v tailscale >/dev/null 2>&1; then
  echo "$(date) fpp_install: installing tailscale" >> "$LOG"
  curl -fsSL https://tailscale.com/install.sh | sh >> "$LOG" 2>&1
fi
systemctl enable --now tailscaled >> "$LOG" 2>&1
# Let the FPP web user drive tailscale, so the customer's "Connect" button works
# (the web UI runs as 'fpp', not root).
tailscale set --operator=fpp >> "$LOG" 2>&1 || true

# --- Provisioning dir for the auth key / order number (root-only) ---
install -d -m 0700 /etc/ldp

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
