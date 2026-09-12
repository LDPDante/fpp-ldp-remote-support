#!/bin/bash
# Triggered from the plugin page's "Apply now" button (POST /api/command/LDP Remote Apply).
# Makes Tailscale match the current on/off setting.
PLUGIN_DIR="/home/fpp/media/plugins/fpp-ldp-remote-support"
. "${PLUGIN_DIR}/scripts/ldp_lib.sh"
ldp_apply
