#!/usr/bin/env python3
"""
Generate a printable "Connect to LDP Support" card (with QR) for a controller.

Usage:
    python make_connect_card.py "Chilutti 1285"            # white card, black text (print-friendly, default)
    python make_connect_card.py --dark "Chilutti 1285"     # dark brand card (for screen)
    python make_connect_card.py "Chilutti 1285" "Smith 1286"   # several at once

For each name it writes <hostname>-card.png in the current folder. The QR opens
that controller's LDP Remote Support page and connects it automatically
(?enable=1) -- the customer just scans it with a phone on the same Wi-Fi.

The <hostname> is derived exactly like the plugin does (lowercase, non-alnum ->
hyphen), so it matches the unit's own name. Set the FPP system hostname to the
same thing so <hostname>.local resolves.

One-time setup:  pip install "qrcode[pil]" pillow
"""
import sys, re

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
except ImportError:
    print('Missing "qrcode". Install once with:  pip install "qrcode[pil]" pillow')
    sys.exit(1)
from PIL import Image, ImageDraw, ImageFont

PLUGIN = "fpp-ldp-remote-support"
GOLD = (232, 184, 75)
DARKNUM = (20, 20, 22)   # number text drawn on the gold circles (both themes)

def theme(dark):
    if dark:
        return {'bg': (10, 11, 14), 'ink': (237, 234, 226), 'sub': (196, 191, 180),
                'eye': GOLD, 'qr': (10, 11, 14), 'panel': (255, 255, 255), 'panel_outline': None}
    return {'bg': (255, 255, 255), 'ink': (20, 20, 22), 'sub': (90, 88, 84),
            'eye': (20, 20, 22), 'qr': (17, 17, 17), 'panel': None, 'panel_outline': (220, 220, 220)}

def hostname(name):
    return re.sub(r'[^a-z0-9]+', '-', name.strip().lower()).strip('-')[:63]

def font(paths, size):
    for p in paths:
        try: return ImageFont.truetype(p, size)
        except Exception: pass
    return ImageFont.load_default()

def make_card(unit, dark=False):
    c = theme(dark)
    host = hostname(unit)
    addr = f"{host}.local"
    url  = f"http://{addr}/plugin.php?plugin={PLUGIN}&page=ldp_remote.php&enable=1"

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=12, border=1)
    qr.add_data(url); qr.make(fit=True)
    qimg = qr.make_image(fill_color=c['qr'], back_color=(255, 255, 255)).convert("RGB")

    W, H = 1200, 1680
    card = Image.new("RGB", (W, H), c['bg'])
    d = ImageDraw.Draw(card)
    f_eye  = font(["C:/Windows/Fonts/segoeui.ttf", "arial.ttf"], 30)
    f_word = font(["C:/Windows/Fonts/segoeuib.ttf", "arialbd.ttf"], 54)
    f_h1   = font(["C:/Windows/Fonts/segoeuib.ttf", "arialbd.ttf"], 82)
    f_num  = font(["C:/Windows/Fonts/segoeuib.ttf", "arialbd.ttf"], 34)
    f_step = font(["C:/Windows/Fonts/segoeui.ttf", "arial.ttf"], 42)
    f_small= font(["C:/Windows/Fonts/segoeui.ttf", "arial.ttf"], 32)

    def ctr(text, y, fnt, fill):
        w = d.textlength(text, font=fnt); d.text(((W - w) / 2, y), text, font=fnt, fill=fill)

    d.rectangle([0, 0, W, 12], fill=GOLD)
    ctr("L  D E S I G N S  P L U S", 66, f_eye, c['eye'])
    ctr("Remote Support", 108, f_word, c['ink'])
    ctr("Scan to connect", 235, f_h1, c['ink'])

    q = 600
    qimg = qimg.resize((q, q), Image.NEAREST)
    qx = (W - q) // 2; qy = 380; pad = 38
    if c['panel']:
        d.rounded_rectangle([qx - pad, qy - pad, qx + q + pad, qy + q + pad], radius=26, fill=c['panel'])
    else:
        d.rounded_rectangle([qx - pad, qy - pad, qx + q + pad, qy + q + pad], radius=26,
                            outline=c['panel_outline'], width=2)
    card.paste(qimg, (qx, qy))

    sx = 210; sy = qy + q + pad + 70
    for i, text in enumerate(["Plug the controller into your router",
                              "Scan this code (same Wi-Fi)",
                              "Connected \u2014 we can help remotely"], 1):
        d.ellipse([sx, sy, sx + 56, sy + 56], fill=GOLD)
        nw = d.textlength(str(i), font=f_num)
        d.text((sx + 28 - nw / 2, sy + 8), str(i), font=f_num, fill=DARKNUM)
        d.text((sx + 78, sy + 7), text, font=f_step, fill=c['ink'])
        sy += 84

    ctr(f"Or type:  {addr}", sy + 18, f_small, c['sub'])
    ctr(f"Unit: {host}", H - 150, f_small, c['sub'])
    ctr("Questions?  support@dvlight.com", H - 104, f_small, c['sub'])
    d.rectangle([0, H - 12, W, H], fill=GOLD)

    out = f"{host}-card.png"
    card.save(out)
    print(f"  wrote {out}   (QR -> {url})")

def main():
    args = sys.argv[1:]
    dark = False
    if "--dark" in args:
        dark = True
        args = [a for a in args if a != "--dark"]
    if not args:
        print('Usage: python make_connect_card.py [--dark] "Customer LastName Order#" [more names...]')
        sys.exit(1)
    for n in args:
        make_card(n, dark)

if __name__ == "__main__":
    main()
