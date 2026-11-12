#!/bin/bash
# Keep internet traffic on the interface that actually reaches the internet.
# Installed as /usr/local/sbin/ldp-route, run at boot and every 2 minutes by
# ldp-route.timer, and by the plugin at install / FPPD start.
#
# A controller often has two default routes: the prop network (Ethernet, a router
# with no internet, or a dead gateway) and the customer's WiFi. With equal metrics
# the kernel can pick the dead one, so downloads, NTP and Tailscale fail. We pin
# the working one with a low metric (50). DHCP renewals and network restarts can
# drop that pin, and the working interface can change (WiFi lost, Ethernet gains
# internet), so this re-checks instead of setting it once.
#
# Quiet when nothing changes: logs only when the outcome differs from last time.
LOG="/home/fpp/media/logs/plugin-fpp-ldp-remote-support.log"
STATE="/run/ldp-route.last"
PIN=50

IP="ip"
[ "$(id -u)" -ne 0 ] && IP="sudo -n ip"

note() {
  # log a message only when it differs from the last one we logged
  [ "$(cat "$STATE" 2>/dev/null)" = "$1" ] && return 0
  echo "$1" > "$STATE" 2>/dev/null
  echo "$(date '+%Y-%m-%d %H:%M:%S') route: $1" >> "$LOG" 2>/dev/null
}

# does this interface reach the internet? ICMP first; some networks block ping,
# so fall back to any HTTP answer from a well-known address (no DNS needed)
reaches() {
  ping -c1 -W3 -I "$1" 1.1.1.1 >/dev/null 2>&1 && return 0
  curl -s -o /dev/null -m5 --interface "$1" http://1.1.1.1/ >/dev/null 2>&1
}

# default routes as "gw dev metric"
defaults() {
  ip -4 route show default 2>/dev/null | awk '{
    gw=""; dev=""; m=0
    for (i = 1; i <= NF; i++) {
      if ($i == "via") gw = $(i+1)
      if ($i == "dev") dev = $(i+1)
      if ($i == "metric") m = $(i+1)
    }
    if (gw != "" && dev != "") print gw, dev, m
  }'
}

# 1. Our pinned route still works -> nothing to do.
pinned="$(defaults | awk -v p="$PIN" '$3 == p { print $1, $2; exit }')"
if [ -n "$pinned" ]; then
  if reaches "${pinned##* }"; then
    note "internet via ${pinned% *} dev ${pinned##* }"
    exit 0
  fi
  $IP route del default via "${pinned% *}" dev "${pinned##* }" metric "$PIN" 2>/dev/null
  echo "$(date '+%Y-%m-%d %H:%M:%S') route: pinned route via ${pinned% *} dev ${pinned##* } stopped reaching the internet; removed" >> "$LOG" 2>/dev/null
fi

# 2. Only one way out -> nothing to choose.
mapfile -t routes < <(defaults | awk '{ print $1, $2 }' | sort -u)
[ "${#routes[@]}" -le 1 ] && { rm -f "$STATE"; exit 0; }

# 3. Pin the first one that reaches the internet.
for r in "${routes[@]}"; do
  gw="${r% *}"; dev="${r##* }"
  if reaches "$dev"; then
    if $IP route replace default via "$gw" dev "$dev" metric "$PIN" 2>/dev/null; then
      note "internet via $gw dev $dev"
    else
      note "could not pin internet route via $gw dev $dev (not root?)"
    fi
    exit 0
  fi
done
note "${#routes[@]} default routes but none reached the internet"
exit 0
