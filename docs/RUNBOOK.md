# LDP Remote Support — Field Runbook

Operational reference for supporting L Designs Plus Ready-to-Run FPP controllers
remotely. Companion to the plugin [README](../README.md).

---

## Reaching a controller

Once a unit is connected (customer clicked **Connect**, or a rental provisioned
`default_enabled=True`), it shows up in the Tailscale console
(console.tailscale.com) under its device name.

- **Web UI:** `http://<100.x tailscale IP>/` — or on the LAN, `http://<name>.local/`
  (the `.local` name is the FPP **system hostname**, which you set at flash time;
  it is *not* the Tailscale name).
- **SSH, passwordless (Tailscale SSH):** `ssh fpp@<100.x>` or `ssh root@<100.x>`
  (needs the `ssh` ACL block — see README).
- **xLights FPP Connect:** Tools → FPP Connect → **Add FPP** → the `100.x` IP.
  mDNS auto-discovery does NOT cross Tailscale, so add it by IP.
- **HTTP API** (no login on the LAN/tailnet): `http://<ip>/api/...` —
  `fppd/status`, `testmode`, `configfile/<name>.json`, `models`, `system/info`.

**On the LDP bench** (same LAN), drive installs/updates from a Windows box with the
**Posh-SSH** PowerShell module: login `fpp` / `falcon`, and `echo falcon | sudo -S`
for root. Base64-encode multi-line scripts to avoid quoting issues.

---

## Provisioning a new unit

Full steps in the README. In short, drop files in `/etc/ldp/` at flash time
(`tailscale.authkey` required; `name` = console/device name; `default_enabled=True`
for rentals), then install via the Plugin Manager URL or `git clone` +
`scripts/fpp_install.sh`. Print a connect card:

```
python tools/make_connect_card.py "Chilutti 1285"
```

---

## KNOWN ISSUE — first pixel flashes on every port (FPP 10.0 + DPIPixels)

**Symptom:** the **first pixel** on the pixel-output ports flickers/flashes — at
idle, during a sequence, **and even during a uniform display test**. Everything
downstream is fine. It's **chip-dependent**: some pixels tolerate it (no flash),
others don't — so it can appear on some props/ports and not others on the same
controller. Known-good strings, and the same strings working on another
controller, all point back to **this** controller.

**Do NOT chase** the strings, ports, wiring, channel config, or null pixels — it's
none of those.

**Root cause:** FPP **10.0's** DPIPixels driver retunes the DPI refresh rate
per-sequence, causing DRM modeset glitches on the Pi's DPI output that corrupt
pixel #1. Hits Raspberry Pi (e.g. Pi 3B+) + **PiCap-v2 / DPIPixels**. Not present
in FPP 7–9. Refs: FPP GitHub issues **#2876** and **#2868**.

**Confirm it (rule out software) via the HTTP API:**
- `GET /api/fppd/status` → `mode=player status=idle` (idle = FPP is blanking outputs)
- `GET /api/testmode` → `{"enabled":0}` (no saved test running)
- `GET /api/configfile/co-universes.json` → no E1.31/DDP input configured
- No active overlay effect; `co-pixelStrings.json` port config correct, no channel overlap

If all of that is clean and FPP is idle (sending all-zeros) yet the first pixel
still flashes → it is the driver bug, not your setup.

**Fix:** the corrected timing is in FPP **master/nightly** (confirmed working); it
is **not** in the 10.0 release. Update FPP to master (below), or wait for the
**10.1** stable release.

---

## Updating FPP remotely (to master, or back to a release)

Use FPP's own scripts — they do it correctly (rebase onto the branch's upstream +
submodules + `upgrade_config` + compile). Run as **root** and **detached**
(`setsid`/`nohup`) so a dropped SSH can't interrupt the compile (~20–40 min on a
Pi 3B+).

```bash
cd /opt/fpp
git config --system --add safe.directory /opt/fpp
git fetch origin --tags
git checkout master               # or a release branch, e.g. v10.1
/opt/fpp/scripts/git_pull         # fetch+rebase upstream, submodules, upgrade_config, compile
systemctl restart fppd
```

Notes:
- **Do NOT reboot mid-compile** — it leaves `fppd` half-built and breaks the unit.
  Wait for the log's `fpp-update FINISH ... (rc=0)` and the fppd restart.
- A large migration may re-show the FPP **initial-setup wizard** and ask for a
  reboot afterward — that's normal; complete it and reboot.
- After reboot: verify `git -C /opt/fpp rev-parse --abbrev-ref HEAD`, that `fppd`
  is running, and confirm the fix on the pixels.
- **Back to stable later:** `git checkout v10.1` (the release branch) then
  `/opt/fpp/scripts/git_pull`.
- Fresh controllers can boot with a **bogus clock**, which breaks TLS to GitHub —
  set the time / enable NTP first. (`fpp_install.sh` now waits for a sane clock.)

---

## Field gotchas (seen in the wild)

- **Dual-gateway / no internet:** a dual-homed controller (prop LAN + internet WiFi)
  gets two default routes; the prop router's DHCP gateway has no internet →
  intermittent connectivity and Tailscale failures. The plugin **self-heals** on
  boot (prefers the internet-capable default route). Admin PCs (Windows) are fixed
  by raising the dead interface's metric.
- **SSH rate-limiting:** many rapid SSH connects can make sshd start refusing
  connections — fall back to the **HTTP API** (port 80), which stays reachable, or
  pace your connections.
- **IP changes on reboot** (DHCP): find the unit by its `<name>.local` mDNS name
  (filter for the IPv4 answer, ignore link-local IPv6) or its stable Tailscale
  `100.x` address.
