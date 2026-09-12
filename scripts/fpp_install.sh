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

# --- Provisioning dir for the auth key / order number (root-only) ---
install -d -m 0700 /etc/ldp

# --- Default the toggle to ON on first install ---
SETTINGS_FILE="/home/fpp/media/config/plugin.${PLUGIN_NAME}"
if ! grep -q 'RemoteSupportEnabled' "$SETTINGS_FILE" 2>/dev/null; then
  echo 'RemoteSupportEnabled = "True"' >> "$SETTINGS_FILE"
  chown fpp:fpp "$SETTINGS_FILE" 2>/dev/null
fi

# --- If enabled and a key has been provisioned, connect now ---
. "${PLUGIN_DIR}/scripts/ldp_lib.sh"
if ldp_enabled; then ldp_apply; fi

# Commands are only read at fppd startup -> ask for a restart.
setSetting restartFlag 1 2>/dev/null
echo "$(date) fpp_install: done" >> "$LOG"
exit 0
