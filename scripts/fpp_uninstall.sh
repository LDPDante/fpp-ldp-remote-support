#!/bin/bash
# Runs as ROOT. Reverses out-of-tree changes. Safe to run more than once.
set +e
. ${FPPDIR}/scripts/common 2>/dev/null
PLUGIN_NAME="fpp-ldp-remote-support"
TS="/usr/bin/tailscale"
: "${LOGDIR:=/home/fpp/media/logs}"
LOG="${LOGDIR}/plugin-${PLUGIN_NAME}.log"
echo "$(date) fpp_uninstall: starting" >> "$LOG"

# Disconnect and remove this node from the tailnet.
$TS logout >> "$LOG" 2>&1
$TS down   >> "$LOG" 2>&1

# We intentionally leave the tailscale package + /etc/ldp in place (they may be
# reused if the plugin is reinstalled). To fully remove Tailscale as well:
#   systemctl disable --now tailscaled
#   apt-get remove -y tailscale
#   rm -rf /etc/ldp /var/lib/tailscale

setSetting restartFlag 1 2>/dev/null
echo "$(date) fpp_uninstall: done" >> "$LOG"
exit 0
