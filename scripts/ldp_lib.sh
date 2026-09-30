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

ldp_log() { { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$PLUGIN_LOG"; } 2>/dev/null; }

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

# Is remote support enabled? (FPP setting RemoteSupportEnabled, default False,
# so a missing/unreadable settings file never connects an opt-in unit)
ldp_enabled() {
  local v="False" line
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
    # file: form keeps the key out of the process list
    $TS up --ssh --accept-dns=false --hostname="$host" --auth-key="file:$LDP_KEYFILE" >>"$PLUGIN_LOG" 2>&1 \
      && ldp_forget_key
  else
    ldp_log "connecting as $host"
    $TS up --ssh --accept-dns=false --hostname="$host" >>"$PLUGIN_LOG" 2>&1
  fi
}

# Has this node enrolled? (has its own node key: Running, or Stopped after 'down')
ldp_enrolled() {
  $TS status --json 2>/dev/null | grep -qE '"BackendState":[[:space:]]*"(Running|Stopped)"'
}

# Once enrolled the node reconnects with its own node key, so the shared auth key
# is no longer needed -- delete it so it can't be copied off the unit.
# /etc/ldp is root-owned: works as root, or as fpp via FPP's passwordless sudo.
ldp_forget_key() {
  [ -e "$LDP_KEYFILE" ] || return 0
  ldp_enrolled || return 0
  if rm -f "$LDP_KEYFILE" 2>/dev/null || sudo -n rm -f "$LDP_KEYFILE" 2>/dev/null; then
    ldp_log "enrolled; removed provisioned auth key"
  fi
}

ldp_down() { ldp_log "disconnecting"; $TS down >>"$PLUGIN_LOG" 2>&1; }

# Ensure the provisioned auth key is readable by the fpp web user, so the
# customer "Connect" button (which runs as fpp) can enroll with it. Root-only;
# no-op if there is no key or we aren't root.
ldp_fix_key_perms() {
  if [ -f "$LDP_KEYFILE" ]; then
    chgrp fpp /etc/ldp "$LDP_KEYFILE" 2>/dev/null
    chmod 750 /etc/ldp 2>/dev/null
    chmod 640 "$LDP_KEYFILE" 2>/dev/null
  fi
  ldp_forget_key
  # the log must be writable by the fpp web user (apply.sh runs as fpp)
  touch "$PLUGIN_LOG" 2>/dev/null
  chown fpp:fpp "$PLUGIN_LOG" 2>/dev/null
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

# Clock-battery stand-in (see ldp_clock.sh). Root-only. Copies the script and
# units out of the (fpp-writable) plugin dir so root never runs files fpp can edit.
ldp_install_clock() {
  local plugin_dir; plugin_dir="$(dirname "${BASH_SOURCE[0]}")"
  install -m 0755 "$plugin_dir/ldp_clock.sh" /usr/local/sbin/ldp-clock || return 1
  install -m 0644 "$plugin_dir"/systemd/ldp-clock*.service "$plugin_dir"/systemd/ldp-clock-save.timer \
    /etc/systemd/system/ || return 1
  systemctl daemon-reload
  systemctl enable ldp-clock.service ldp-clock-save.timer >/dev/null 2>&1
  systemctl start ldp-clock.service ldp-clock-save.timer >/dev/null 2>&1
  /usr/local/sbin/ldp-clock save
  ldp_log "clock: installed save/restore service"
}

ldp_remove_clock() {
  systemctl disable --now ldp-clock-save.timer ldp-clock.service >/dev/null 2>&1
  rm -f /etc/systemd/system/ldp-clock.service /etc/systemd/system/ldp-clock-save.service \
        /etc/systemd/system/ldp-clock-save.timer /usr/local/sbin/ldp-clock
  systemctl daemon-reload
}

# Bench provisioning applied once per unit (a marker file stops it overriding
# anything the customer changes later). Root-only.
#   /etc/ldp/timezone -> e.g. America/Chicago (system + FPP TimeZone setting)
#   /etc/ldp/playlist -> playlist to start on every power-up (FPPD_STARTED preset),
#                        so the show runs even when the clock is wrong offline
LDP_TZFILE="/etc/ldp/timezone"
LDP_PLAYLISTFILE="/etc/ldp/playlist"

ldp_apply_provisioning() {
  local tz pl settings="${MEDIADIR}/settings" presets="${MEDIADIR}/config/commandPresets.json"
  if [ -r "$LDP_TZFILE" ] && [ ! -e /etc/ldp/.timezone_applied ]; then
    tz="$(tr -d '[:space:]' < "$LDP_TZFILE")"
    if [ -n "$tz" ] && [ -f "/usr/share/zoneinfo/$tz" ]; then
      timedatectl set-timezone "$tz" 2>/dev/null
      if grep -q '^TimeZone[[:space:]]*=' "$settings" 2>/dev/null; then
        sed -i "s|^TimeZone[[:space:]]*=.*|TimeZone = \"$tz\"|" "$settings"
      else
        echo "TimeZone = \"$tz\"" >> "$settings"
      fi
      chown fpp:fpp "$settings" 2>/dev/null
      touch /etc/ldp/.timezone_applied
      ldp_log "provision: timezone $tz"
    else
      ldp_log "provision: unknown timezone '$tz' in $LDP_TZFILE, skipped"
    fi
  fi
  if [ -r "$LDP_PLAYLISTFILE" ] && [ ! -e /etc/ldp/.playlist_applied ]; then
    pl="$(head -n1 "$LDP_PLAYLISTFILE" | tr -d '\r')"
    if [ -n "$pl" ] && python3 - "$presets" "$pl" <<'PY'
import json, sys
path, playlist = sys.argv[1], sys.argv[2]
try:
    with open(path) as f: data = json.load(f)
except Exception:
    data = {"commands": []}
cmds = data.setdefault("commands", [])
if not any(c.get("name") == "FPPD_STARTED" for c in cmds):
    cmds.append({"name": "FPPD_STARTED", "command": "Start Playlist",
                 "args": [playlist, "true", "true", "false"],
                 "multisyncCommand": False, "multisyncHosts": "", "presetSlot": 0})
    with open(path, "w") as f: json.dump(data, f, indent="\t")
PY
    then
      chown fpp:fpp "$presets" 2>/dev/null
      touch /etc/ldp/.playlist_applied
      ldp_log "provision: FPPD_STARTED preset -> '$pl'"
    fi
  fi
}

# Fix routing first, then make Tailscale match the on/off setting.
ldp_apply() {
  ldp_prefer_internet_route
  if ldp_enabled; then ldp_up; else ldp_down; fi
}
