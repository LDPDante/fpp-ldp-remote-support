#!/bin/bash
# fppd ExecStartPost hook. Runs on every boot/restart AFTER the network is up
# (fppd is ordered After=fpp_postnetwork.service, which waits for an IP).
# Must return quickly, so apply the on/off state in the background.
. ${FPPDIR}/scripts/common 2>/dev/null
PLUGIN_DIR="/home/fpp/media/plugins/fpp-ldp-remote-support"
nohup bash -c ". '${PLUGIN_DIR}/scripts/ldp_lib.sh'; ldp_apply" >/dev/null 2>&1 &
exit 0
