#!/usr/bin/env python3
"""
Generate a phone-friendly "which prop goes on which port" map from an xLights show.

Usage:
    python make_port_map.py Z:\\Halloween                      # every controller in the show
    python make_port_map.py Z:\\Halloween --controller F16v4   # just one (repeatable)
    python make_port_map.py Z:\\Halloween --title "Riardos Halloween"

Writes <show>-portmap.html in the current folder: one self-contained page (no
internet needed) listing, per controller, each port -> smart receiver -> props
in chain order with pixel counts, and start/end null pixels as their own lines
exactly where they sit in the wiring. Save it to your phone, or print it
for the inside of the controller lid. Controllers only remember the first prop
on a port; xLights knows the whole chain, so this reads xLights.

Reads xlights_networks.xml + xlights_rgbeffects.xml from the show folder.
No extra packages needed.
"""
import argparse, html, os, re, sys
import xml.etree.ElementTree as ET
from datetime import datetime

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

def esc(s):
    return html.escape(str(s))

def render(title, show, ctrls, unassigned):
    secs = []
    for c in ctrls:
        nports = PORTS.get(c['model'].upper().replace('_', '-'), 0)
        used = sorted({p for p, _ in c['ports']})
        nports = max([nports] + used) if used else nports
        cards = []
        for port in range(1, nports + 1):
            keys = sorted(k for k in c['ports'] if k[0] == port)
            if not keys:
                cards.append(f'<div class="port empty"><div class="ph"><b>Port {port}</b><span>empty</span></div></div>')
                continue
            for _, remote in keys:
                props = c['ports'][(port, remote)]
                nulls = sum(p['null'] + p['endnull'] for p in props)
                total = sum(p['pixels'] for p in props) + nulls
                rows = []
                def null_row(n, where):
                    return (f'<li class="null"><span class="n">∅</span><span class="nm">{n} null pixel{"s" if n != 1 else ""}'
                            f'<small>{where}</small></span><span class="px">{n}</span></li>')
                for i, p in enumerate(props, 1):
                    if p['null']:
                        rows.append(null_row(p['null'], f'before {esc(p["name"])}'))
                    rows.append(f'<li><span class="n">{i}</span><span class="nm">{esc(p["name"])}'
                                + (f'<small>{esc(" · ".join(p["notes"]))}</small>' if p['notes'] else '')
                                + f'</span><span class="px">{p["pixels"]}</span></li>')
                    if p['endnull']:
                        rows.append(null_row(p['endnull'], f'after {esc(p["name"])}'))
                rlabel = f' <em>Receiver {remote}</em>' if remote else ''
                ntxt = f' ({nulls} null)' if nulls else ''
                cards.append(f'<div class="port"><div class="ph"><b>Port {port}</b>{rlabel}'
                             f'<span>{len(props)} prop{"s" if len(props) != 1 else ""} · {total} px{ntxt}</span></div>'
                             f'<ol>{"".join(rows)}</ol></div>')
        dmx = ''
        if c['dmx']:
            items = ''.join(f'<li><span class="nm">{esc(d["name"])}</span><span class="px">DMX {esc(d["ch"])}'
                            f'{"–" + str(int(d["ch"]) + d["width"] - 1) if str(d["ch"]).isdigit() and d["width"] > 1 else ""}</span></li>'
                            for d in sorted(c['dmx'], key=lambda d: int(d['ch']) if str(d['ch']).isdigit() else 0))
            dmx = f'<div class="port dmx"><div class="ph"><b>DMX</b><span>{len(c["dmx"])} fixtures</span></div><ul>{items}</ul></div>'
        sub = ' · '.join(x for x in (f"{c['vendor']} {c['model']}".strip(), c['ip'], f"{c['pixels']} px") if x)
        secs.append(f'<section><h2>{esc(c["name"])}</h2><p class="sub">{esc(sub)}</p>'
                    f'<div class="grid">{"".join(cards)}{dmx}</div></section>')
    un = (f'<p class="warn">Not assigned to a controller: {esc(", ".join(unassigned))}</p>' if unassigned else '')
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} Port Map</title>
<style>
:root{{--bg:#fff;--card:#f6f5f2;--ink:#1a1a1c;--sub:#5f5d58;--line:#dcd9d2;--acc:#b8860b;--empty:#a9a69f}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#111214;--card:#1c1d20;--ink:#ecebe6;--sub:#a5a39c;--line:#2e2f33;--acc:#e8b84b;--empty:#5d5c58}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.35 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:16px}}
h1{{font-size:22px;margin:0 0 2px}}h2{{font-size:18px;margin:22px 0 0}}.sub,.meta{{color:var(--sub);margin:2px 0 10px;font-size:13px}}
.grid{{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}}
.port{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;break-inside:avoid}}
.ph{{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}}.ph b{{font-size:17px;color:var(--acc)}}.ph em{{font-style:normal;font-weight:600}}
.ph span{{margin-left:auto;color:var(--sub);font-size:13px}}
.empty{{padding:6px 12px;opacity:.75}}.empty b{{color:var(--empty);font-size:15px}}
ol,ul{{list-style:none;margin:6px 0 0;padding:0}}li{{display:flex;gap:8px;padding:5px 0;border-top:1px solid var(--line)}}
.n{{min-width:20px;height:20px;border-radius:50%;background:var(--acc);color:#141416;font-size:12px;font-weight:700;display:grid;place-items:center;flex:none}}
.nm{{flex:1;min-width:0;overflow-wrap:anywhere}}.nm small{{display:block;color:var(--sub)}}.px{{color:var(--sub);font-variant-numeric:tabular-nums;white-space:nowrap}}
li.null{{color:var(--sub)}}li.null .n{{background:none;color:var(--acc);border:1.5px dashed var(--acc);font-size:11px}}li.null .nm{{font-weight:600;color:var(--ink)}}
.warn{{color:#b3261e;font-size:13px}}
@media print{{body{{padding:0;font-size:12px}}.grid{{grid-template-columns:repeat(3,1fr);gap:6px}}.port{{padding:6px 8px}}h2{{break-before:page}}section:first-of-type h2{{break-before:auto}}}}
</style></head><body>
<h1>{esc(title)}</h1><p class="meta">Port map from xLights show <b>{esc(show)}</b> · generated {stamp} · props listed in wiring order (1 = closest to the controller); ∅ = null pixels, wire them in exactly where shown</p>
{un}{"".join(secs)}
</body></html>'''

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('show', help='xLights show folder')
    ap.add_argument('--controller', '-c', action='append', help='only this controller (name as in xLights)')
    ap.add_argument('--title', help='page title (default: show folder name)')
    ap.add_argument('--out', help='output file (default: <show>-portmap.html)')
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
    title = args.title or base
    out = args.out or re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-') + '-portmap.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(render(title, show, picked, unassigned if not args.controller else []))
    for c in picked:
        print(f"  {c['name']}: {len(c['ports'])} port groups, {c['pixels']} px, {len(c['dmx'])} DMX")
    print(f'  wrote {out}')

if __name__ == '__main__':
    main()
