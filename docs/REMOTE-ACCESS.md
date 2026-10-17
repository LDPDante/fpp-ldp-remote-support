# Remote Access Procedure — session handoff

For an AI coding session (or a technician) picking up LDP remote support work from the
LDP bench PC. Read this first; the [RUNBOOK](RUNBOOK.md) has the known issues and fixes,
the [README](../README.md) has provisioning. State below is as of **2026-10-17**.

---

## 1. Ground rules (learned the hard way)

- **Read-only first.** Probe with the HTTP API / read-only SSH before changing anything,
  and say what you found. Ask before anything that changes how a unit behaves at a
  customer site (network, schedule, FPP version, reboot during a show).
- **Never change a unit's WiFi** unless the user explicitly asks — LDP101's WiFi is set
  for the Riardos site on purpose, even when it sits on the bench with no internet.
- **Secrets stay put.** The Tailscale auth key lives in `tailscale.txt` in the repo root
  (gitignored). Don't read or print it — this environment's permission checks block it.
  If a unit needs the key, give the user a command that pipes it straight to the unit
  (see §6).
- **Customer data never goes in git:** `exports/`, `*-portmap*.html`, `*-card*.png`,
  `fleetmap/units.json`, `fleetmap/cache.json` are gitignored. Keep it that way.
- **Some remote writes get blocked** by this environment's permission checks (e.g.
  changing a unit's network config over SSH, deleting files). When that happens, stop
  and give the user the exact FPP-UI steps instead; don't route around it.
- Commits end with the `Co-Authored-By` line the session's instructions give; push to
  `main` only when the user asks or it's an established pattern for the change.

---

## 2. The tools on the bench PC

| What | Where / how |
|---|---|
| Bench PC | Windows 10, Tailscale name `desktop-6tim3g6`, **100.69.208.54**; LAN `192.168.0.63` (Ethernet, bench network, no internet) + `172.20.6.x` (WiFi, internet) |
| Shells | PowerShell (primary) and Git Bash |
| SSH | PowerShell module **Posh-SSH** (no `sshpass`). Units: user `fpp`, password `falcon`; root via `echo falcon \| sudo -S …` |
| Tailscale CLI | `C:\Program Files\Tailscale\tailscale.exe` (not on PATH) |
| Python | 3.14 on PATH (repo tools are stdlib-only, except `make_connect_card.py`: `qrcode`, `pillow`) |
| PHP | `C:\Users\PC3\tools\php83\php.exe` (lint/test plugin pages locally) |
| Screenshots | headless Edge: `msedge.exe --headless=new --screenshot=… <url>` (min window width ~500 px — wrap pages in a fixed-width `<iframe>` to check phone layout) |
| xLights shows | NAS `Z:\` = `\\nas\L Designs Plus`. Riardos: **`E:\RiardosXlights`** (local drive; `Z:\Halloween` is gone). Chilutti: `Z:\Chilutti-1285\Chiliutti26` |

Standard SSH call (multi-line scripts: here-string; avoid `rm` of `/tmp/...` paths in
the command text — a local safety check misreads them as local deletions):

```powershell
Import-Module Posh-SSH
$c = New-Object PSCredential('fpp',(ConvertTo-SecureString 'falcon' -AsPlainText -Force))
$s = New-SSHSession -ComputerName 100.80.226.33 -Credential $c -AcceptKey -Force -WarningAction SilentlyContinue -ConnectionTimeout 15
(Invoke-SSHCommand -SSHSession $s -Command 'uptime -p; vcgencmd get_throttled' -TimeOut 60).Output
Remove-SSHSession $s | Out-Null
```

Copy a file to a unit: `Set-SCPItem -ComputerName <ip> -Credential $c -AcceptKey -Force -Path <local> -Destination /tmp`.

---

## 3. How to reach a unit — decision tree

1. **Is it online in Tailscale?**
   `& 'C:\Program Files\Tailscale\tailscale.exe' status` → look for the unit's name.
   - **online / active** → use its `100.x` address for everything below.
   - **offline, last seen …** → it has no internet, is powered off, or remote support
     is switched off. Nothing to do remotely; tell the user and wait.
2. **On the bench instead?** Try its LAN IP (LDP101: `192.168.0.201`) from this PC's
   Ethernet side. Works with no internet on the unit — but then the unit can't reach
   GitHub/NTP either (see §5 "updating without internet").
3. **Then pick the channel:**

| Need | Use |
|---|---|
| FPP web UI | `http://<100.x>/` |
| Quick status, no login | HTTP API: `/api/fppd/status`, `/api/system/info`, `/api/configfile/<file>.json`, `/api/proxies`, `/api/fppd/schedule` |
| Shell | SSH as `fpp` (port 22 is allowed by the `tag:fpp` ACL); password login works over Tailscale |
| A controller behind the Pi (Falcon, Kulp) | FPP proxy: `http://<100.x>/proxy/<controller-ip>/` (keep the trailing `/`; add the IP under Content Setup → Proxy Settings first). Falcon V4 needs `Accept-Encoding: gzip` from scripts |
| Which prop is on which port | Plugin **Port Map**: `http://<100.x>/plugin.php?plugin=fpp-ldp-remote-support&page=portmap.php` (`&nopage=1` = phone view; `&format=json` = live data; `&view=saved` = map pushed from xLights) |
| xLights | Tools → FPP Connect → Add FPP → the `100.x` IP (mDNS doesn't cross Tailscale) |

**First look at any unit** (read-only, one SSH call):

```bash
uptime -p; date; timedatectl | grep -E 'zone|synchron'
ip -4 -br addr | grep -v '^lo'; ip -4 route | grep default
vcgencmd get_throttled; vcgencmd measure_temp
tailscale status --self --peers=false | head -1
cd /home/fpp/media/plugins/fpp-ldp-remote-support && git log --oneline -1 && git status -s
curl -s localhost/api/fppd/status | head -c 400
```

Read `throttled`: `0x0` clean · `0x50000` under-voltage happened earlier (check
`dmesg | grep -i voltage` for when) · `0x50005` under-voltage **now**.

---

## 4. Unit inventory (Tailscale `tag:fpp` = controllers)

| Unit | Tailscale | What / where | Notes |
|---|---|---|---|
| **ldp101** | 100.80.226.33 | LDP-owned (not for sale). Riardos Halloween show. Pi 3B+, FPP 10.2, host `LDP101` | eth0 **static 192.168.0.201, no gateway** → Falcon **F16V4 192.168.0.106** (static, fw Bld 38, proxied). Internet only via WiFi **"Riardos"** (don't change). Auto-connect on (`/etc/ldp/default_enabled=True`). TZ America/New_York. Schedule: *Riardos Halloween*, every day 00:00–24:00, repeat. Brief under-voltage dips in the first minute after boot only (LRS-350 + buck; suggest buck 5.15–5.2 V at the Pi / heavier leads). Plugin updated 2026-10-17 to `main` (has the **live Port Map**, `614717a`); its Port Map page reads the F16 directly. Ports 7/8 show a red "names look older" note until models are re-uploaded from xLights FPP Connect. Saved map from `Z:\Halloween` (old). Over the `nyc` relay, **SSH (Posh-SSH) times out** while HTTP works fine — use the HTTP API |
| **chilutti-1285** | 100.114.172.12 | Customer Chilutti. Pi 3B+ + PiCap v2, FPP 10 master | Offline since ~2026-09-29. No RTC battery → `FPPD_STARTED` preset starts *Chilutti Christmas* at power-up; ldp-clock service installed 2026-09-29 but **never verified on the unit**. TZ America/Chicago. **Pending when it's back:** check `ldp-clock` service + saved time, preset, TZ, last boot's `fppd.log`; then fix the update block once: `git checkout -- scripts/ldp_clock.sh && git pull` (and `sudo chown fpp:fpp .git/FETCH_HEAD` if needed). Customer says he sent a "designer show file" — not found on the PC or NAS as of 2026-10-09 |
| ldp-pi4-3 | 100.79.59.83 | LDP controller (Pi 4) | Offline since ~2026-09-20; role unknown |
| ldp-f0c1a59e… | 100.73.4.26 | LDP controller, unnamed | Offline since ~2026-09-13; role unknown |

Admin devices (not controllers): `desktop-6tim3g6` (this bench PC), `x99screamer`,
`buffer`, `riardos` (Windows), `pixel-8` (phone).

---

## 5. Common jobs

**Install remote support on a new unit** — README "Provisioning" + "Install". Needs
internet on the unit. Before running `scripts/fpp_install.sh`, make sure the clock is
real (it now waits for NTP itself) and the default route goes out the interface with
internet (it fixes that itself too). The key goes in `/etc/ldp/tailscale.authkey`
(§6); the plugin deletes it after enrolling. Verify with `tailscale status --json`
(`BackendState: Running`).

**Update the plugin on a unit**
- Online: FPP Plugin Manager → Update; from the bench PC: `curl -X POST http://<100.x>/api/plugin/fpp-ldp-remote-support/upgrade` (same thing, works when SSH won't connect; returns `{"Status":"OK"}`); or as `fpp` in the plugin dir: `git pull`.
  Check it took: `...&page=portmap.php&nopage=1&format=json` returns JSON (`"live":true`) on the new version, a web page on the old one.
- **No internet (e.g. on the bench):** from the repo on this PC
  `git bundle create <scratch>\ldp.bundle <unit's commit>..main` → `Set-SCPItem` to
  `/tmp` → on the unit, in the plugin dir: `git fetch -q /tmp/ldp.bundle main && git merge --ff-only -q FETCH_HEAD`.

**Push a port map** — `python tools/make_port_map.py <show folder> -c <controller> --title "<name>" --push <100.x or LAN IP>`
(needs plugin with `portmap.php` on the unit). QR card: `python tools/make_connect_card.py --portmap "<unit name>"`.

**Show not playing** — `fppd.log`: a `Stop Now` means someone stopped it and it holds
until the next schedule slot (RUNBOOK "Field gotchas"); otherwise check the clock /
scheduler hold (RUNBOOK "show doesn't start offline").

**Low-voltage warning** — `vcgencmd get_throttled` + `dmesg | grep -i voltage` with
timestamps; boot-only dips vs continuous tell you supply sag vs a bad supply.

**Fleet map** (all Tailscale devices on a map) — `python fleetmap\fleetmap.py`, serves
`http://100.69.208.54:8080/` to the tailnet only. Locations/roles in
`fleetmap/units.json` (gitignored). **Open items:** it isn't auto-started (a session
background task gets killed — needs a Startup-folder launcher with `pythonw`, user
hasn't approved yet); Windows Firewall needs an inbound rule for TCP 8080 from
`100.64.0.0/10` (admin, user runs it); no addresses filled in yet.

---

## 6. Getting the Tailscale key onto a unit (without reading it)

Give the user this to run in their own PowerShell (they type the `fpp` password):

```powershell
$k = (Select-String -Path C:\Users\PC3\fpp-ldp-remote-support\tailscale.txt -Pattern 'tskey-auth-[A-Za-z0-9-]+').Matches[0].Value
ssh fpp@<unit-ip> "echo falcon | sudo -S sh -c 'install -d -m 0700 /etc/ldp && echo $k > /etc/ldp/tailscale.authkey && chmod 600 /etc/ldp/tailscale.authkey && wc -c /etc/ldp/tailscale.authkey'"
```

~62 bytes back = key in place. The current key is reusable, `tag:fpp`, expires
**2026-12-10** — a new one is needed for units provisioned after that.

---

## 7. Where things are

- Plugin code: repo root (`ldp_remote.php`, `portmap.php`, `portmap/`, `scripts/`, `commands/`)
- Bench tools: `tools/` (`make_connect_card.py`, `make_port_map.py`)
- Fleet map: `fleetmap/`
- On a unit: plugin `/home/fpp/media/plugins/fpp-ldp-remote-support`, provisioning
  `/etc/ldp/`, plugin log `/home/fpp/media/logs/plugin-fpp-ldp-remote-support.log`,
  saved port map `/home/fpp/media/config/ldp-portmap.json`, FPP log
  `/home/fpp/media/logs/fppd.log`
