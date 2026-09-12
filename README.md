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
2. (Optional) Add the order number so the unit is easy to find in the Tailscale console:
   ```
   echo '1042' | sudo tee /etc/ldp/order >/dev/null
   ```
3. **Choose the shipped default** (the runtime toggle stays selectable either way):
   - **Sales unit — opt-in (default):** do nothing. It ships OFF; the customer clicks
     "Connect to LDP Support" to connect.
   - **Rental unit — auto-connect on power-up:** provision it ON:
     ```
     echo True | sudo tee /etc/ldp/default_enabled >/dev/null
     ```
     Now it connects to your tailnet automatically every time it powers up (as long as it
     has internet) — no click needed.
4. Rotate/replace FPP's default `fpp` password before shipping.

The key is only needed for the **first** connection; after enrollment the unit reconnects with
its own stored node key. You may delete `/etc/ldp/tailscale.authkey` after first enrollment.

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
- To enable **passwordless Tailscale SSH** into units (used by the `--ssh` flag), add this block
  to the policy (Access controls -> JSON editor):
  ```jsonc
  "ssh": [
    { "action": "accept", "src": ["autogroup:member"], "dst": ["tag:fpp"], "users": ["fpp", "root"] }
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
— which connects on open. Put it on the instruction card as a link or a **QR code** the
customer scans with a phone on the same WiFi. `&disable=1` turns it back off.

**Make `fpp.local` reliable:** the URL resolves via mDNS to the controller's *system*
hostname (separate from its Tailscale name). At flash time, keep a **consistent system
hostname** (leave the FPP default `FPP` → `fpp.local`, or set a branded one like
`ldp-controller` → `ldp-controller.local`) so the same link works on every unit. If a
customer has several controllers, tell them to use the IP from their router instead.

**No account/app for the customer:** the auth key lives on the device, so connecting needs
no Tailscale login, no software install — just the click.
