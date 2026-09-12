#!/bin/bash
# Shared helpers for the LDP Remote Support plugin. Sourced by the other scripts.

PLUGIN_NAME="fpp-ldp-remote-support"
TS="/usr/bin/tailscale"

: "${MEDIADIR:=/home/fpp/media}"
: "${LOGDIR:=/home/fpp/media/logs}"
PLUGIN_LOG="${LOGDIR}/plugin-${PLUGIN_NAME}.log"

# Provisioning files written at flash time (root-only). Never committed to the repo.
LDP_KEYFILE="/etc/ldp/tailscale.authkey"     # contains: tskey-auth-....
LDP_ORDERFILE="/etc/ldp/order"               # optional: an order number to prefix the name

SETTINGS_FILE="${MEDIADIR}/config/plugin.${PLUGIN_NAME}"

ldp_log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$PLUGIN_LOG" 2>/dev/null; }

# Hardware serial: device-tree first (Pi/BBB), then cpuinfo, then machine-id.
ldp_serial() {
  local s=""
  if [ -r /sys/firmware/devicetree/base/serial-number ]; then
    s="$(tr -d '\000' < /sys/firmware/devicetree/base/serial-number 2>/dev/null)"
  fi
  if [ -z "$s" ] && [ -r /proc/cpuinfo ]; then
    s="$(awk -F': ' '/^Serial/ {print $2; exit}' /proc/cpuinfo 2>/dev/null)"
  fi
  if [ -z "$s" ] && [ -r /etc/machine-id ]; then
    s="$(cat /etc/machine-id 2>/dev/null)"
  fi
  echo "$s" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9'
}

# Tailscale device name: ldp-<order>-<serial>, or ldp-<serial> if no order file.
ldp_hostname() {
  local serial order name
  serial="$(ldp_serial)"; [ -z "$serial" ] && serial="unknown"
  order=""
  [ -r "$LDP_ORDERFILE" ] && order="$(tr -cd 'a-zA-Z0-9-' < "$LDP_ORDERFILE" 2>/dev/null | tr '[:upper:]' '[:lower:]')"
  if [ -n "$order" ]; then name="ldp-${order}-${serial}"; else name="ldp-${serial}"; fi
  echo "$name" | cut -c1-63
}

# Is remote support enabled? (FPP setting RemoteSupportEnabled, default True)
ldp_enabled() {
  local v="True" line
  if [ -r "$SETTINGS_FILE" ]; then
    line="$(grep -E '^[[:space:]]*RemoteSupportEnabled[[:space:]]*=' "$SETTINGS_FILE" | tail -n1)"
    [ -n "$line" ] && v="$(echo "$line" | sed -E 's/^[^=]*=[[:space:]]*"?([^"]*)"?[[:space:]]*$/\1/')"
  fi
  case "$v" in True|true|1|on|On) return 0 ;; *) return 1 ;; esac
}

# Bring Tailscale up. Enroll with the provisioned key on first run; reconnect after.
ldp_up() {
  local host; host="$(ldp_hostname)"
  if ! $TS status --peers=false >/dev/null 2>&1 && [ -r "$LDP_KEYFILE" ]; then
    ldp_log "enrolling as $host with provisioned key"
    $TS up --ssh --accept-dns=false --hostname="$host" --authkey="$(cat "$LDP_KEYFILE")" >>"$PLUGIN_LOG" 2>&1
  else
    ldp_log "connecting as $host"
    $TS up --ssh --accept-dns=false --hostname="$host" >>"$PLUGIN_LOG" 2>&1
  fi
}

ldp_down() { ldp_log "disconnecting"; $TS down >>"$PLUGIN_LOG" 2>&1; }

# Make Tailscale match the on/off setting.
ldp_apply() { if ldp_enabled; then ldp_up; else ldp_down; fi; }
