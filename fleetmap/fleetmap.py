#!/usr/bin/env python3
"""
LDP Fleet Map - every Tailscale device on a map: where it is, online/offline,
its name, and what it does. Served from this PC, reachable only over Tailscale.

Run:   python fleetmap\\fleetmap.py            (then open the URL it prints)
       python fleetmap\\fleetmap.py --port 8080 --bind 100.69.208.54

Live status comes from the local `tailscale status --json` (no API key).
What each unit is and where it is comes from fleetmap/units.json (yours to edit;
customer data, not in git - copy units.example.json to start). Location, best first:
  1. "lat"/"lng" in units.json                     -> exact
  2. "address" in units.json, geocoded (OpenStreetMap) -> exact
  3. the device's public IP while Tailscale sees it  -> approximate (city)
  4. a direct LAN connection to this PC              -> same site as this PC
Anything else is listed as "no location yet" (with its Tailscale relay region as
a hint - that's chosen by network speed, so too unreliable to pin).
Lookups are cached in fleetmap/cache.json so a unit keeps its pin when offline.
"""
import argparse, json, os, re, subprocess, sys, threading, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
UNITS = os.path.join(HERE, 'units.json')
CACHE = os.path.join(HERE, 'cache.json')
TS = r'C:\Program Files\Tailscale\tailscale.exe' if os.name == 'nt' else 'tailscale'
UA = 'LDP-FleetMap/1.0 (L Designs Plus support tool)'

# Tailscale DERP relay regions -> rough coordinates (fallback only)
DERP = {'nyc': (40.71, -74.01, 'New York area'), 'chi': (41.88, -87.63, 'Chicago area'),
        'dfw': (32.78, -96.80, 'Dallas area'), 'den': (39.74, -104.99, 'Denver area'),
        'mia': (25.76, -80.19, 'Miami area'), 'atl': (33.75, -84.39, 'Atlanta area'),
        'sea': (47.61, -122.33, 'Seattle area'), 'sfo': (37.77, -122.42, 'San Francisco area'),
        'lax': (34.05, -118.24, 'Los Angeles area'), 'ord': (41.88, -87.63, 'Chicago area'),
        'tor': (43.65, -79.38, 'Toronto area'), 'hou': (29.76, -95.37, 'Houston area'),
        'iad': (38.95, -77.45, 'Washington DC area'), 'phx': (33.45, -112.07, 'Phoenix area')}

_lock = threading.Lock()

def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default

def load_cache():
    c = load_json(CACHE, {})
    for k in ('geo', 'ip', 'last'):
        c.setdefault(k, {})
    return c

def save_cache(cache):
    tmp = CACHE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=1)
    os.replace(tmp, CACHE)

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))

def geocode(address):
    q = urllib.parse.urlencode({'q': address, 'format': 'json', 'limit': 1})
    res = fetch_json('https://nominatim.openstreetmap.org/search?' + q)
    if res:
        return {'lat': float(res[0]['lat']), 'lng': float(res[0]['lon'])}
    return None

def ip_locate(ip):
    res = fetch_json(f'https://ipwho.is/{urllib.parse.quote(ip)}')
    if res.get('success'):
        place = ', '.join(x for x in (res.get('city'), res.get('region_code') or res.get('region')) if x)
        return {'lat': res['latitude'], 'lng': res['longitude'], 'place': place}
    return None

def public_ip(peer):
    for a in [peer.get('CurAddr') or ''] + list(peer.get('Addrs') or []):
        ip = re.sub(r':\d+$', '', a).strip('[]')
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip) and not re.match(
                r'^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.|169\.254\.)', ip):
            return ip
    return None

def tailscale_status():
    out = subprocess.run([TS, 'status', '--json'], capture_output=True, timeout=15,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return json.loads(out.stdout.decode('utf-8'))

def ago(ts):
    if not ts or ts.startswith('0001'):
        return None
    try:
        t = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError:
        return None
    return int((datetime.now(timezone.utc) - t).total_seconds())

def devices():
    st = tailscale_status()
    units = load_json(UNITS, {})
    cache = load_cache()
    selfnode = dict(st.get('Self') or {}, Online=True, _self=True)
    peers = [selfnode] + list((st.get('Peer') or {}).values())
    out, dirty, self_loc = [], False, None
    for p in peers:
        host = (p.get('HostName') or '?')
        key = host.lower()
        dns = (p.get('DNSName') or '').split('.')[0].lower()
        u = units.get(dns) or units.get(key) or {}
        tags = list(p.get('Tags') or [])
        ip4 = next((a for a in p.get('TailscaleIPs') or [] if '.' in a), '')
        loc = None
        if 'lat' in u and 'lng' in u:
            loc = {'lat': u['lat'], 'lng': u['lng'], 'source': 'set', 'approx': False, 'place': u.get('address', '')}
        elif u.get('address'):
            g = cache['geo'].get(u['address'])
            if g:
                loc = dict(g, source='address', approx=False, place=u['address'])
        if not loc:
            pub = public_ip(p)
            if pub:
                g = cache['ip'].get(pub)
                if g:
                    loc = dict(g, source='ip', approx=True)
                    if cache['last'].get(dns or key) != loc:
                        cache['last'][dns or key] = loc; dirty = True
            if not loc and cache['last'].get(dns or key):
                loc = dict(cache['last'][dns or key], source='ip (last seen)')
        # a direct LAN connection to this PC means it's at the same site
        if not loc and self_loc and not p.get('_self') and re.match(
                r'^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)', p.get('CurAddr') or ''):
            loc = dict(self_loc, source='same network as this PC')
        if p.get('_self'):
            self_loc = loc
        # Tailscale's relay region is picked by latency, not location - too unreliable
        # to pin; it's only shown as a hint for units with no location yet.
        relay = p.get('Relay') or ''
        hint = DERP[relay][2] if not loc and relay in DERP else ''
        out.append({
            'name': u.get('label') or dns or host, 'host': host, 'dns': p.get('DNSName', '').rstrip('.'),
            'ip': ip4, 'os': p.get('OS', ''), 'online': bool(p.get('Online')), 'active': bool(p.get('Active')),
            'self': bool(p.get('_self')), 'lastSeenAgo': None if p.get('Online') else ago(p.get('LastSeen', '')),
            'tags': tags, 'controller': 'tag:fpp' in tags, 'relay': relay, 'hint': hint,
            'role': u.get('role', ''), 'customer': u.get('customer', ''), 'links': u.get('links', {}),
            'location': loc, '_pub': public_ip(p), '_addr': u.get('address', '')})
    if dirty:
        with _lock:
            latest = load_cache()
            latest['last'].update(cache['last'])
            save_cache(latest)
    return out

def resolver_loop():
    """Background: geocode new addresses / public IPs (rate-limited, cached)."""
    while True:
        try:
            known = load_cache()
            new_geo, new_ip = {}, {}
            for d in devices():
                if d['_addr'] and d['_addr'] not in known['geo'] and d['_addr'] not in new_geo:
                    new_geo[d['_addr']] = geocode(d['_addr']) or {}
                    time.sleep(1.1)                          # Nominatim: max 1 request/second
                if d['_pub'] and d['_pub'] not in known['ip'] and d['_pub'] not in new_ip:
                    new_ip[d['_pub']] = ip_locate(d['_pub']) or {}
                    time.sleep(1.1)
            if new_geo or new_ip:
                with _lock:                                  # merge into the latest copy
                    cache = load_cache()
                    cache['geo'].update(new_geo); cache['ip'].update(new_ip)
                    save_cache(cache)
        except Exception as e:                              # keep serving even if a lookup fails
            print(f'  lookup error: {e}', file=sys.stderr)
        time.sleep(60)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ('/', '/index.html'):
            with open(os.path.join(HERE, 'index.html'), 'rb') as f:
                return self.send(200, f.read(), 'text/html; charset=utf-8')
        if path == '/api/devices':
            try:
                devs = devices()
            except Exception as e:
                return self.send(500, json.dumps({'error': str(e)}).encode(), 'application/json')
            for d in devs:
                d.pop('_pub', None); d.pop('_addr', None)
                if d['location']:
                    d['location'] = {k: v for k, v in d['location'].items() if v not in ({}, None)} or None
                    if d['location'] and 'lat' not in d['location']:
                        d['location'] = None
            body = {'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'devices': devs}
            return self.send(200, json.dumps(body).encode(), 'application/json')
        self.send(404, b'not found', 'text/plain')

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--bind', help="address to listen on (default: this PC's Tailscale IP, so only the tailnet can reach it)")
    args = ap.parse_args()
    bind = args.bind
    if not bind:
        out = subprocess.run([TS, 'ip', '-4'], capture_output=True, text=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        bind = out.stdout.strip().splitlines()[0] if out.stdout.strip() else ''
        if not bind:
            sys.exit('Tailscale is not running on this PC (no 100.x address). Start Tailscale first.')
    if not os.path.exists(UNITS):
        print(f'  note: no {UNITS} yet - copy units.example.json to units.json and fill it in')
    threading.Thread(target=resolver_loop, daemon=True).start()
    srv = ThreadingHTTPServer((bind, args.port), Handler)
    print(f'  LDP Fleet Map:  http://{bind}:{args.port}/   (Tailscale only; Ctrl+C to stop)')
    srv.serve_forever()

if __name__ == '__main__':
    main()
