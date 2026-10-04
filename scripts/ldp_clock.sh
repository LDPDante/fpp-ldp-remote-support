#!/bin/bash
# Software stand-in for a clock battery. Installed as /usr/local/sbin/ldp-clock.
#   save    - remember the current time (timer every 10 min, and at shutdown)
#   restore - at boot, move the clock forward to the last saved time
# Without an RTC battery a Pi boots with a stale clock (e.g. the image date), and
# FPP 10 holds the scheduler until the date is past its release. Restoring the
# last-known time gets past that check offline; NTP corrects it once online.
# Only ever moves the clock FORWARD, so a working RTC or NTP time always wins.
STATE="/var/lib/ldp/clock"

saved() { local s; s="$(cat "$STATE" 2>/dev/null)"; case "$s" in ''|*[!0-9]*) echo 0 ;; *) echo "$s" ;; esac; }

case "$1" in
  save)
    now="$(date +%s)"
    # NTP-verified time always wins (clears any bad saved value); otherwise only move forward
    synced="$(timedatectl show -p NTPSynchronized --value 2>/dev/null)"
    if [ "$synced" = "yes" ] || [ "$now" -gt "$(saved)" ]; then
      mkdir -p "$(dirname "$STATE")"
      echo "$now" > "$STATE.tmp" && mv -f "$STATE.tmp" "$STATE"
    fi
    ;;
  restore)
    s="$(saved)"
    if [ "$s" -gt "$(date +%s)" ]; then
      date -s "@$s" >/dev/null && logger -t ldp-clock "clock restored to last saved time $(date)"
    fi
    ;;
  *) echo "usage: $0 save|restore" >&2; exit 2 ;;
esac
exit 0
