#!/usr/bin/env python3
"""
Generate a printable "Connect to LDP Support" card (with QR) for a controller.

Usage:
    python make_connect_card.py "Chilutti 1285"
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
DARK=(10,11,14); GOLD=(232,184,75); INK=(237,234,226); SUB=(196,191,180)

def hostname(name):
    return re.sub(r'[^a-z0-9]+', '-', name.strip().lower()).strip('-')[:63]

def font(paths, size):
    for p in paths:
        try: return ImageFont.truetype(p, size)
        except Exception: pass
    return ImageFont.load_default()

def make_card(unit):
    host = hostname(unit)
    addr = f"{host}.local"
    url  = f"http://{addr}/plugin.php?plugin={PLUGIN}&page=ldp_remote.php&enable=1"

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=12, border=1)
    qr.add_data(url); qr.make(fit=True)
    qimg = qr.make_image(fill_color=DARK, back_color=(255,255,255)).convert("RGB")

    W, H = 1200, 1680
    card = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(card)
    f_eye  = font(["C:/Windows/Fonts/segoeui.ttf","arial.ttf"], 30)
    f_word = font(["C:/Windows/Fonts/segoeuib.ttf","arialbd.ttf"], 54)
    f_h1   = font(["C:/Windows/Fonts/segoeuib.ttf","arialbd.ttf"], 82)
    f_num  = font(["C:/Windows/Fonts/segoeuib.ttf","arialbd.ttf"], 34)
    f_step = font(["C:/Windows/Fonts/segoeui.ttf","arial.ttf"], 42)
    f_small= font(["C:/Windows/Fonts/segoeui.ttf","arial.ttf"], 32)

    def ctr(text, y, fnt, fill):
        w = d.textlength(text, font=fnt); d.text(((W-w)/2, y), text, font=fnt, fill=fill)

    d.rectangle([0,0,W,12], fill=GOLD)
    ctr("L  D E S I G N S  P L U S", 66, f_eye, GOLD)
    ctr("Remote Support", 108, f_word, INK)
    ctr("Scan to connect", 235, f_h1, INK)

    q = 600
    qimg = qimg.resize((q,q), Image.NEAREST)
    qx = (W-q)//2; qy = 380; pad = 38
    d.rounded_rectangle([qx-pad,qy-pad,qx+q+pad,qy+q+pad], radius=26, fill=(255,255,255))
    card.paste(qimg, (qx,qy))

    sx = 210; sy = qy+q+pad+70
    for i, text in enumerate(["Plug the controller into your router",
                              "Scan this code (same Wi-Fi)",
                              "Connected \u2014 we can help remotely"], 1):
        d.ellipse([sx,sy,sx+56,sy+56], fill=GOLD)
        nw = d.textlength(str(i), font=f_num)
        d.text((sx+28-nw/2, sy+8), str(i), font=f_num, fill=DARK)
        d.text((sx+78, sy+7), text, font=f_step, fill=INK)
        sy += 84

    ctr(f"Or type:  {addr}", sy+18, f_small, SUB)
    ctr(f"Unit: {host}", H-150, f_small, GOLD)
    ctr("Questions?  support@dvlight.com", H-104, f_small, SUB)
    d.rectangle([0,H-12,W,H], fill=GOLD)

    out = f"{host}-card.png"
    card.save(out)
    print(f"  wrote {out}   (QR -> {url})")

def main():
    names = sys.argv[1:]
    if not names:
        print('Usage: python make_connect_card.py "Customer LastName Order#" [more names...]'); sys.exit(1)
    for n in names:
        make_card(n)

if __name__ == "__main__":
    main()
