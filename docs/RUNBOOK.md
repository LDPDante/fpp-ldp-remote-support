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
for rentals; `timezone` = customer's zone, e.g. `America/Chicago`; `playlist` = show
playlist to start on every power-up), then install via the Plugin Manager URL or
`git clone` + `scripts/fpp_install.sh`. Print a connect card:

```
python tools/make_connect_card.py "Chilutti 1285"
```

**Port map for setup day** — controllers only remember the *first* prop on a port;
xLights knows the whole chain. From the show folder:

```
python tools/make_port_map.py Z:\Halloween --title "Riardos Halloween"
python tools/make_port_map.py Z:\Halloween --controller F16v4   # one controller
python tools/make_port_map.py Z:\Halloween -c F16v4 --title "Riardos Halloween" --push 100.80.226.33
python tools/make_connect_card.py --portmap "LDP101"            # + QR card for the lid
```

Writes `<show>-portmap.html`: per port (and smart receiver), the props in wiring
order with pixel counts, **start/end null pixels as their own lines** where they
sit, color order / brightness / reversed notes, empty ports, DMX fixtures, and
models not assigned to any controller. Self-contained, works offline — AirDrop or
email it to your phone, or print it for the controller lid.

**On the controller:** `--push <IP | name.local | 100.x>` uploads it to the
plugin's **Status/Control → Port Map** page (or use that page's *Upload map*
button with the `.html`). Phone view: `http://<name>.local/plugin.php?plugin=fpp-ldp-remote-support&page=portmap.php&nopage=1`
— that's what the `--portmap` card's QR opens. Stored as
`/home/fpp/media/config/ldp-portmap.json`, so plugin updates keep it. Re-push
after any xLights wiring change. "No Port Map page yet" from `--push` = update the
plugin on that unit first.

---

## KNOWN ISSUE — show doesn't start offline (stale clock, FPP 10)

**Symptom:** the show only starts once the controller gets internet (e.g. when the
customer connects to support). **Cause:** no working RTC battery (PiCap v2 kernel log:
`rtc-ds1307 ... oscillator failed`), so the Pi boots with a stale date and FPP 10 logs
`Clock appears incorrect ... delaying scheduler start until time sync`.

**Fixes (the plugin does 1 and 2 automatically):**
1. `ldp-clock` service saves the time every 10 min and restores it at boot, so the
   date is past FPP's check. Check with `systemctl status ldp-clock ldp-clock-save.timer`.
2. `FPPD_STARTED` command preset (from `/etc/ldp/playlist`) starts the show on every
   power-up regardless of the clock. Confirmed working offline on chilutti-1285.
3. Real fix: a CR2032 in the PiCap, then the RTC keeps true time.

Also check the timezone (`/etc/ldp/timezone`) — chilutti-1285 shipped on New_York
instead of Chicago.

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
  set the time / enable NTP first. (`fpp_install.sh` now waits for a real NTP sync;
  a plausible-looking year like the image date is still too old for today's certs.)

---

## Reaching a Falcon (or other controller) behind the Pi

The Pi's Tailscale address reaches the Pi only — not the controllers on its prop
network. Use **FPP's built-in proxy** instead; it rides on port 80, which the
`tag:fpp` ACL already allows, so no Tailscale changes are needed.

1. On the Pi: **Content Setup → Proxy Settings** → add the controller's IP (e.g.
   `192.168.0.106`), Save. (API: `POST /api/proxies/<ip>`.)
2. Open `http://<pi 100.x>/proxy/<controller ip>/` — keep the trailing `/`.

Works fully on a Falcon F16V4 (Bld 38): pages, status, and settings/save (its UI
builds the API URL from the page address, so calls stay on the proxy).
Example: LDP101 → `http://100.80.226.33/proxy/192.168.0.106/`.

- **Proxy only reaches the IP listed.** If the controller's IP changes, or someone
  edits the entry (LDP101's was once overwritten with `10.50.0.1`), you get an
  Apache **"404 Not Found"** page. Check the list: `GET /api/proxies`.
- **Falcon V4 returns 404 for `/` to curl / scripts** — it only stores gzipped
  pages. Browsers are fine; in scripts add `-H 'Accept-Encoding: gzip'`.
  `/status.xml` works without it and is a quick "is it alive" check.
- On customer units, proxy **only their light controllers** — never their router
  or other home devices.

---

## Wiring: Pi straight to a Falcon, internet over WiFi (no router)

Prop network on the cable, internet on WiFi. The show runs over the cable even if
the internet drops; remote support comes and goes with the WiFi.

| | Setting |
|---|---|
| **Pi eth0** (FPP → Network → eth0) | **Static** `192.168.0.201` / `255.255.255.0` |
| **Pi gateway** (FPP → Network → Global Network Settings) | **blank** — so internet goes out WiFi |
| **Pi DNS** | `1.1.1.1` / `8.8.8.8` (FPP warns if empty on a static interface) |
| **Pi wlan0** | the site's WiFi (set *before* it leaves the bench) |
| **Falcon wired** (Network tab) | **Enable DHCP unchecked**, `192.168.0.106` / `255.255.255.0`, gateway `0.0.0.0` |

- **Both ends must be static** — with no router nothing hands out addresses, and a
  DHCP Pi just has no eth0 IP.
- Any normal Ethernet cable; both ends auto-detect.
- **Bench test:** an F16V4's two Ethernet ports are an internal switch — Pi into
  one, bench router into the other, and you can reach both from the bench while
  Pi↔F16 traffic takes the same path it will on site.
- Set the Falcon's IP while it's still on the bench router; once it's cabled only
  to the Pi, the bench PC can't reach it (except via the proxy).
- Falcon **WiFi hotspot**: turn it off unless you want a phone/laptop backdoor at
  the site; if you keep it, don't leave its passphrase on show in screenshots.

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
- **Plugin won't update** (`git pull`: "local changes to scripts/ldp_clock.sh would
  be overwritten"): units installed before `9e8e577` show that file modified (only
  its executable bit). Fix once over SSH as `fpp`:
  `cd /home/fpp/media/plugins/fpp-ldp-remote-support && git checkout -- scripts/ldp_clock.sh && git pull`
  If git says `.git/FETCH_HEAD: Permission denied`, first
  `sudo chown fpp:fpp .git/FETCH_HEAD`.
- **"Raspberry Pi Voltage Too Low"** (FPP warning 15): check `vcgencmd get_throttled`
  — `0x0` is clean; `0x50005` = under-voltage and throttling *right now*. Fix the
  supply (Pi 3B+: 5.1V/2.5A, short thick cable), then Restart FPPD to clear it.
- **Scheduled show won't restart after a manual Stop** (FPP 10): stopping a
  scheduled playlist ends that schedule slot. Pressing Start on the *same*
  playlist logs `StartPlaylistAtCommand: Deferring to scheduler` and nothing
  plays until the next slot — for an all-day schedule, that's midnight. Not a
  broken schedule: **Restart FPPD** (or reboot) and it starts the current slot.
  Check `fppd.log` for `Stop Now` to see when it was stopped.
- **IP changes on reboot** (DHCP): find the unit by its `<name>.local` mDNS name
  (filter for the IPv4 answer, ignore link-local IPv6) or its stable Tailscale
  `100.x` address.
