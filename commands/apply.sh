#!/bin/bash
# Triggered by the plugin page's Connect/Disconnect links (and on boot via postStart).
# Makes Tailscale match the current on/off setting.
export PATH="/usr/sbin:/sbin:/usr/bin:/bin:$PATH"   # so 'ip' is found when run as the web user
PLUGIN_DIR="/home/fpp/media/plugins/fpp-ldp-remote-support"
. "${PLUGIN_DIR}/scripts/ldp_lib.sh"
ldp_apply
