#!/bin/bash
# Shared helpers for the LDP Remote Support plugin. Sourced by the other scripts.

PLUGIN_NAME="fpp-ldp-remote-support"
TS="/usr/bin/tailscale"

: "${MEDIADIR:=/home/fpp/media}"
: "${LOGDIR:=/home/fpp/media/logs}"
PLUGIN_LOG="${LOGDIR}/plugin-${PLUGIN_NAME}.log"

# Provisioning files written at flash time (root-only). Never committed to the repo.
LDP_KEYFILE="/etc/ldp/tailscale.authkey"     # contains: tskey-auth-....
LDP_NAMEFILE="/etc/ldp/name"                 # optional: human label / show position -> device name
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

# Tailscale device name, in priority order:
#   1. /etc/ldp/name  -> a human label / show position ("Driveway Left props")
#   2. /etc/ldp/order -> ldp-<order>-<serial>
#   3. ldp-<serial>
ldp_hostname() {
  local serial order name label
  if [ -r "$LDP_NAMEFILE" ]; then
    label="$(cat "$LDP_NAMEFILE" 2>/dev/null)"
    if [ -n "$label" ]; then
      # sanitize to a DNS-safe hostname: lowercase, non-alnum -> hyphen, trim
      name="$(printf '%s' "$label" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed -E 's/-+/-/g; s/^-+//; s/-+$//')"
      if [ -n "$name" ]; then echo "$name" | cut -c1-63; return; fi
    fi
  fi
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

# Ensure the provisioned auth key is readable by the fpp web user, so the
# customer "Connect" button (which runs as fpp) can enroll with it. Root-only;
# no-op if there is no key or we aren't root.
ldp_fix_key_perms() {
  [ -f "$LDP_KEYFILE" ] || return 0
  chgrp fpp /etc/ldp "$LDP_KEYFILE" 2>/dev/null
  chmod 750 /etc/ldp 2>/dev/null
  chmod 640 "$LDP_KEYFILE" 2>/dev/null
}

# If there are multiple default routes, prefer the one that actually reaches the
# internet, and deprioritize any that don't (e.g. a prop network whose router
# advertises itself as a gateway but has no internet). Both interfaces stay fully
# up; only the *internet* default route is pinned. No-op on single-homed hosts.
ldp_prefer_internet_route() {
  local defs entry gw dev goodgw gooddev n
  mapfile -t defs < <(ip -4 route show default 2>/dev/null \
    | awk '{gw="";dev="";for(i=1;i<=NF;i++){if($i=="via")gw=$(i+1);if($i=="dev")dev=$(i+1)} if(gw!=""&&dev!="")print gw" "dev}' \
    | sort -u)
  n=${#defs[@]}
  [ "$n" -le 1 ] && return 0
  for entry in "${defs[@]}"; do
    gw="${entry%% *}"; dev="${entry##* }"
    if ping -c1 -W3 -I "$dev" 1.1.1.1 >/dev/null 2>&1; then goodgw="$gw"; gooddev="$dev"; break; fi
  done
  if [ -n "$gooddev" ]; then
    ip route replace default via "$goodgw" dev "$gooddev" metric 50 2>/dev/null
    ldp_log "route: prefer internet via $goodgw dev $gooddev ($n default routes present)"
  else
    ldp_log "route: $n default routes but none reached the internet"
  fi
}

# Fix routing first, then make Tailscale match the on/off setting.
ldp_apply() {
  ldp_prefer_internet_route
  if ldp_enabled; then ldp_up; else ldp_down; fi
}
