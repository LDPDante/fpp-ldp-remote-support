# fpp-ldp-remote-support

An FPP (Falcon Player) plugin that gives **L Designs Plus** secure remote-support access to
Ready-to-Run controllers via **Tailscale**. When enabled, the controller joins the private LDP
support network so LDP can set it up and troubleshoot remotely. The customer sees an
**"LDP Remote Support"** page in the FPP menu with a toggle and can turn it off any time.

- Reaches the controller's **web UI (port 80)** and **SSH** from LDP's admin machine.
- Each controller is **isolated** (Tailscale ACL `tag:fpp`): LDP can reach it, but it can't
  reach other customers' controllers or LDP's machines.
- The Tailscale auth key is **never** in this repo — it's provisioned per unit at flash time.

## How it works

- `scripts/fpp_install.sh` (root, on install) installs Tailscale and defaults the toggle ON.
- `scripts/postStart.sh` runs on every boot **after the network is up** and applies the toggle
  (connect if enabled, disconnect if not). Once enrolled, `tailscaled` also auto-reconnects on
  its own across reboots.
- `scripts/ldp_lib.sh` holds the logic; `commands/apply.sh` is what the page's "Apply now" runs.
- Device name = the hardware **serial** (`ldp-<serial>`), or `ldp-<order>-<serial>` if an order
  file is provisioned.

## Provisioning (do this at your bench, per unit)

1. Put the **reusable, `tag:fpp` auth key** into a root-only file:
   ```
   sudo install -d -m 0700 /etc/ldp
   echo 'tskey-auth-XXXXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXX' | sudo tee /etc/ldp/tailscale.authkey >/dev/null
   sudo chmod 600 /etc/ldp/tailscale.authkey
   ```
2. (Optional) **Name the controller** so it's easy to identify in the Tailscale console.
   Pick one:
   - By **show position** (best for rentals / multi-controller shows):
     ```
     echo 'Driveway Left props' | sudo tee /etc/ldp/name >/dev/null
     ```
     → appears as `driveway-left-props`.
   - By **order number**:
     ```
     echo '1042' | sudo tee /etc/ldp/order >/dev/null
     ```
     → appears as `ldp-1042-<serial>`.

   With neither it's `ldp-<serial>`. (You can also just rename any machine in the Tailscale
   console at any time.)
3. **Choose the shipped default** (the runtime toggle stays selectable either way):
   - **Sales unit — opt-in (default):** do nothing. It ships OFF; the customer clicks
     "Connect to LDP Support" to connect.
   - **Rental unit — auto-connect on power-up:** provision it ON:
     ```
     echo True | sudo tee /etc/ldp/default_enabled >/dev/null
     ```
     Now it connects to your tailnet automatically every time it powers up (as long as it
     has internet) — no click needed.
4. **Timezone and show start** (recommended). Set the customer's timezone, and the
   playlist to start on every power-up, so the show runs even offline with a wrong clock:
   ```
   echo 'America/Chicago' | sudo tee /etc/ldp/timezone >/dev/null
   echo 'Customer Show Playlist' | sudo tee /etc/ldp/playlist >/dev/null
   ```
   Each is applied once, at install (or the next boot), and never overrides later changes.
   The plugin also installs a small clock save/restore service so a unit with no RTC
   battery still boots with a sane date (see the runbook's "show doesn't start offline").
5. Rotate/replace FPP's default `fpp` password before shipping.

The key is only needed for the **first** connection; after enrollment the unit reconnects with
its own stored node key. The plugin **deletes `/etc/ldp/tailscale.authkey` automatically** once the
unit has enrolled (right after enrolling, and again on every boot), so it can't be copied off the unit.

**Tailscale console hardening (recommended):** turn on **Device Approval** (Settings -> Device
management) so a copied key can't add rogue devices without your approval, and once every
shipped unit has enrolled, **revoke** the shared key and issue a new one for new units.

## Install on a controller

**Via the FPP Plugin Manager (recommended):** Content Setup -> Plugins -> add the repo URL
`https://github.com/LDPDante/fpp-ldp-remote-support.git`, install, then restart FPPD when asked.

**Manual (for quick testing):**
```
cd /home/fpp/media/plugins
sudo -u fpp git clone https://github.com/LDPDante/fpp-ldp-remote-support.git
sudo /home/fpp/media/plugins/fpp-ldp-remote-support/scripts/fpp_install.sh
```

## Tailscale side (one-time, in the LDP tailnet)

- ACL already defines `tag:fpp` and isolates units (admin -> `tag:fpp:22,80,443`).
- To enable **Tailscale SSH** into units (used by the `--ssh` flag), add this to the policy
  (Access controls -> JSON editor). Only listed support staff get in, as `fpp` (use `sudo` for
  root), and `check` makes them re-confirm their Tailscale login every 12h:
  ```jsonc
  "groups": {
    "group:ldp-support": ["you@example.com"]
  },
  "ssh": [
    { "action": "check", "src": ["group:ldp-support"], "dst": ["tag:fpp"], "users": ["fpp"], "checkPeriod": "12h" }
  ]
  ```
  Without it, the web UI (port 80) still works; SSH just won't be reachable until it's added.

## Customer connect flow (opt-in)

Shipped units default to **OFF** — they auto-play their show with no internet and never
phone home. A customer opts into remote support with a plug + a click:

1. Plug an Ethernet cable from their router to the controller (gives it internet).
2. Open **`http://fpp.local/`** on the same network → **LDP Remote Support** page.
3. Click **"Connect to LDP Support"** → the pre-provisioned key enrolls it in ~10s.

**One-click link / QR:** the Connect button is just this URL —
`http://fpp.local/plugin.php?plugin=fpp-ldp-remote-support&page=ldp_remote.php&enable=1`
— which opens the page with the Connect button ready to tap. Put it on the instruction card as
a link or a **QR code** the customer scans with a phone on the same WiFi. Connect/Disconnect
only take effect on a button press carrying a per-unit token, so another website can't silently
connect the controller. `&disable=1` opens it with the Disconnect button highlighted.

**Make `fpp.local` reliable:** the URL resolves via mDNS to the controller's *system*
hostname (separate from its Tailscale name). At flash time, keep a **consistent system
hostname** (leave the FPP default `FPP` → `fpp.local`, or set a branded one like
`ldp-controller` → `ldp-controller.local`) so the same link works on every unit. If a
customer has several controllers, tell them to use the IP from their router instead.

**No account/app for the customer:** the auth key lives on the device, so connecting needs
no Tailscale login, no software install — just the click.
