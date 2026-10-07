#!/usr/bin/env python3
"""
Generate a phone-friendly "which prop goes on which port" map from an xLights show.

Usage:
    python make_port_map.py Z:\\Halloween                      # every controller in the show
    python make_port_map.py Z:\\Halloween --controller F16v4   # just one (repeatable)
    python make_port_map.py Z:\\Halloween --title "Riardos Halloween"
    python make_port_map.py Z:\\Halloween -c F16v4 --push 100.80.226.33   # also put it on the Pi

Writes <show>-portmap.html in the current folder: one self-contained page (no
internet needed) listing, per controller, each port -> smart receiver -> props
in chain order with pixel counts, and start/end null pixels as their own lines
exactly where they sit in the wiring. Save it to your phone, or print it
for the inside of the controller lid. Controllers only remember the first prop
on a port; xLights knows the whole chain, so this reads xLights.

--push also uploads it to that controller's LDP plugin, so it's on the plugin's
Port Map page at <name>.local on site (no internet) and over Tailscale.

Reads xlights_networks.xml + xlights_rgbeffects.xml from the show folder.
No extra packages needed.
"""
import argparse, html, json, os, re, sys, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

PLUGIN = 'fpp-ldp-remote-support'
SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'portmap')

# Known port counts, so empty ports show up too. Others: up to the highest used port.
PORTS = {'F4V4': 4, 'F16V4': 16, 'F48V4': 48, 'F16V5': 16, 'F32V5': 32, 'F48V5': 48,
         'K8-B': 8, 'K16A-B': 16}

def node_count(m):
    """Pixels in one model (all strings), the way xLights counts them."""
    a = m.attrib
    kind = a.get('DisplayAs', '')
    if kind == 'Custom':
        nodes = set()
        cmc = a.get('CustomModelCompressed')
        if cmc:
            for cell in cmc.split(';'):
                n = cell.split(',')[0].strip()
                if n.isdigit():
                    nodes.add(int(n))
        else:
            nodes = {int(n) for n in re.findall(r'\d+', a.get('CustomModel', ''))}
        return len(nodes)
    if a.get('PixelCount', '').isdigit() and kind not in ('Single Line',) and 'Matrix' not in kind:
        return int(a['PixelCount'])
    try:
        return int(a.get('parm1', 1)) * int(a.get('parm2', 0))
    except ValueError:
        return 0

def strings_of(m):
    """(strings, nodes per string) - multi-string models span consecutive ports."""
    a = m.attrib
    kind = a.get('DisplayAs', '')
    if kind == 'Custom' or not a.get('parm1', '').isdigit():
        return 1, node_count(m)
    s = max(1, int(a['parm1']))
    return s, node_count(m) // s

def start_offset(m):
    """Channel offset within its controller, from '!Controller:123'."""
    mt = re.match(r'!.*:(\d+)$', m.get('StartChannel', ''))
    return int(mt.group(1)) if mt else None

def load(show):
    nets = ET.parse(os.path.join(show, 'xlights_networks.xml')).getroot()
    ctrls = {}
    for c in nets.findall('Controller'):
        if c.get('Name') and c.get('IP'):
            ctrls[c.get('Name')] = {'name': c.get('Name'), 'vendor': c.get('Vendor', ''),
                                    'model': c.get('Model', ''), 'variant': c.get('Variant', ''),
                                    'ip': c.get('IP', ''), 'ports': {}, 'dmx': [], 'pixels': 0}
    rgb = ET.parse(os.path.join(show, 'xlights_rgbeffects.xml')).getroot()
    unassigned = []
    for m in rgb.find('models').findall('model'):
        if m.get('Active') == '0':
            continue
        name, cname = m.get('name'), m.get('Controller')
        cc = m.find('ControllerConnection')
        cca = cc.attrib if cc is not None else {}
        if cname not in ctrls or not cca.get('Port', '').isdigit():
            if cname not in ctrls:
                unassigned.append(name)
            continue
        c = ctrls[cname]
        port = int(cca['Port'])
        if not m.get('StringType', 'RGB Nodes').endswith('Nodes') or m.get('DisplayAs', '').startswith('Dmx'):
            ch = cca.get('channel') or str(start_offset(m) or '?')
            try:
                width = int(m.get('parm1', 1))
            except ValueError:
                width = 1
            c['dmx'].append({'name': name, 'port': port, 'ch': ch, 'width': width})
            continue
        nstr, per = strings_of(m)
        base = start_offset(m)
        remote = cca.get('SmartRemote', '')
        remote = chr(ord('A') + int(remote) - 1) if remote.isdigit() and int(remote) > 0 else ''
        notes = []
        if cca.get('colorOrder'):
            notes.append(cca['colorOrder'])
        bright = cca.get('brightness') or cca.get('Brightness')
        if bright:
            notes.append(f"{bright}% bright")
        if cca.get('reverse') == '1':
            notes.append('reversed')
        for s in range(nstr):
            label = name if nstr == 1 else f"{name} (string {s + 1}/{nstr})"
            c['ports'].setdefault((port + s, remote), []).append({
                'name': label, 'model': name, 'pixels': per,
                'null': int(cca.get('nullNodes', 0) or 0) if s == 0 else 0,
                'endnull': int(cca.get('endNullNodes', 0) or 0) if s == nstr - 1 else 0,
                'chain': (m.get('ModelChain') or '').lstrip('>'),
                'start': None if base is None else base + s * per * 3,
                'notes': notes})
        c['pixels'] += nstr * per
    for c in ctrls.values():
        for key, props in c['ports'].items():
            c['ports'][key] = order(props)
    return ctrls, unassigned

def order(props):
    """Chain order: by start channel (xLights assigns it along the chain), else follow ModelChain."""
    if all(p['start'] is not None for p in props):
        return sorted(props, key=lambda p: p['start'])
    by_model = {p['model']: p for p in props}
    out, seen = [], set()
    cur = [p for p in props if p['chain'] not in by_model]
    while cur:
        p = cur.pop(0)
        if id(p) in seen:
            continue
        out.append(p); seen.add(id(p))
        cur = [q for q in props if q['chain'] == p['model'] and id(q) not in seen] + cur
    return out + [p for p in props if id(p) not in seen]

def build_data(title, show, ctrls, unassigned):
    """Plain data for portmap/portmap.js (also what --push sends to the Pi)."""
    out = []
    for c in ctrls:
        nports = PORTS.get(c['model'].upper().replace('_', '-'), 0)
        used = sorted({p for p, _ in c['ports']})
        nports = max([nports] + used) if used else nports
        ports = []
        for port in range(1, nports + 1):
            keys = sorted(k for k in c['ports'] if k[0] == port)
            if not keys:
                ports.append({'port': port, 'remote': '', 'props': []})
            for _, remote in keys:
                ports.append({'port': port, 'remote': remote, 'props': [
                    {k: p[k] for k in ('name', 'pixels', 'null', 'endnull', 'notes')}
                    for p in c['ports'][(port, remote)]]})
        dmx = sorted(c['dmx'], key=lambda d: int(d['ch']) if str(d['ch']).isdigit() else 0)
        out.append({'name': c['name'], 'vendor': c['vendor'], 'model': c['model'], 'ip': c['ip'],
                    'pixels': c['pixels'], 'ports': ports,
                    'dmx': [{'name': d['name'], 'ch': d['ch'], 'width': d['width']} for d in dmx]})
    return {'version': 1, 'title': title, 'show': show,
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'controllers': out, 'unassigned': unassigned}

def standalone(data):
    """Self-contained page: shared CSS + renderer + the data, nothing to download."""
    css = open(os.path.join(SHARED, 'portmap.css'), encoding='utf-8').read()
    js = open(os.path.join(SHARED, 'portmap.js'), encoding='utf-8').read()
    blob = json.dumps(data).replace('<', '\u003c')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(data['title'])} Port Map</title>
<style>{css}
body{{margin:0;padding:16px;background:var(--pm-bg)}}
@media (prefers-color-scheme:dark){{body{{background:#111214}}}}</style></head>
<body class="ldp-pm pm-auto"><div id="pm"></div>
<script>{js}</script>
<script>LDPPortMap.render({blob}, document.getElementById('pm'));</script>
</body></html>"""

def push(data, host):
    """Upload the map to a controller's LDP plugin (same per-unit token as Connect)."""
    base = host if host.startswith('http') else f'http://{host}'
    url = f"{base.rstrip('/')}/plugin.php?plugin={PLUGIN}&page=portmap.php&nopage=1"
    page = urllib.request.urlopen(url, timeout=15).read().decode('utf-8', 'replace')
    tok = re.search(r'data-ldp-token="([0-9a-f]{32,})"', page)
    if not tok:
        sys.exit(f'  push failed: {base} has no Port Map page yet (update the LDP plugin there first)')
    body = urllib.parse.urlencode({'ldp_action': 'portmap_upload', 'ldp_token': tok.group(1),
                                   'portmap': json.dumps(data)}).encode()
    resp = urllib.request.urlopen(urllib.request.Request(url + '&format=json', data=body), timeout=30)
    txt = resp.read().decode('utf-8', 'replace')
    mt = re.search(r'\{"ok".*\}', txt, re.S)
    res = json.loads(mt.group(0)) if mt else {'error': 'unexpected reply from the controller'}
    if not res.get('ok'):
        sys.exit(f"  push failed: {res.get('error', 'unknown error')}")
    print(f"  pushed to {base}  ->  {base}/plugin.php?plugin={PLUGIN}&page=portmap.php&nopage=1")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('show', help='xLights show folder')
    ap.add_argument('--controller', '-c', action='append', help='only this controller (name as in xLights)')
    ap.add_argument('--title', help='page title (default: show folder name)')
    ap.add_argument('--out', help='output file (default: <show>-portmap.html)')
    ap.add_argument('--push', metavar='HOST', help="also upload to this controller's LDP Port Map page (IP, name.local or 100.x)")
    args = ap.parse_args()
    show = os.path.abspath(args.show)
    if not os.path.exists(os.path.join(show, 'xlights_rgbeffects.xml')):
        sys.exit(f'No xlights_rgbeffects.xml in {show}')
    ctrls, unassigned = load(show)
    if args.controller:
        missing = [n for n in args.controller if n not in ctrls]
        if missing:
            sys.exit(f"Unknown controller(s): {', '.join(missing)}. In this show: {', '.join(ctrls)}")
        picked = [ctrls[n] for n in args.controller]
    else:
        picked = [c for c in ctrls.values() if c['ports'] or c['dmx']]
    base = os.path.basename(show.rstrip('\\/')) or 'show'
    data = build_data(args.title or base, show, picked, [] if args.controller else unassigned)
    out = args.out or re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-') + '-portmap.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(standalone(data))
    for c in picked:
        print(f"  {c['name']}: {len(c['ports'])} port groups, {c['pixels']} px, {len(c['dmx'])} DMX")
    print(f'  wrote {out}')
    if args.push:
        push(data, args.push)

if __name__ == '__main__':
    main()
