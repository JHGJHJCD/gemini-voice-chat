#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_icon.py - מייצר אייקון מרשים רב-רזולוציה (app.ico + app.png)."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 1024  # supersample


def lerp(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


# ---- רקע: גרדיאנט אלכסוני טורקיז->ציאן + זוהר רך ----
yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
t = (xx + yy) / (2.0 * S)
c0 = np.array([14, 70, 84], np.float32)     # טורקיז עמוק
c1 = np.array([46, 214, 236], np.float32)   # ציאן בהיר
grad = c0[None, None, :] * (1 - t[..., None]) + c1[None, None, :] * t[..., None]
r = np.sqrt((xx - S * 0.5) ** 2 + (yy - S * 0.30) ** 2) / (S * 0.62)
glow = np.clip(1 - r, 0, 1)[..., None] * np.array([70, 70, 70], np.float32)
grad = np.clip(grad + glow, 0, 255).astype(np.uint8)
bg = Image.fromarray(grad, "RGB").convert("RGBA")

mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1],
                                       radius=int(S * 0.225), fill=255)
icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
icon.paste(bg, (0, 0), mask)

cx = S / 2
cap_w, cap_h = S * 0.215, S * 0.37
left, right = cx - cap_w / 2, cx + cap_w / 2
top = S * 0.205
bottom = top + cap_h
cap_center_y = top + cap_h * 0.42
stroke = S * 0.032

# ---- גלי קול עדינים משני הצדדים ----
waves = Image.new("RGBA", (S, S), (0, 0, 0, 0))
wd = ImageDraw.Draw(waves)
for i, rad in enumerate((cap_w * 0.95, cap_w * 1.45)):
    a = int(150 - i * 55)
    bb = [cx - rad, cap_center_y - rad, cx + rad, cap_center_y + rad]
    wd.arc(bb, start=305, end=360, fill=(255, 255, 255, a), width=int(stroke * 0.85))
    wd.arc(bb, start=0, end=55, fill=(255, 255, 255, a), width=int(stroke * 0.85))
    wd.arc(bb, start=125, end=235, fill=(255, 255, 255, a), width=int(stroke * 0.85))
icon = Image.alpha_composite(icon, waves)

# ---- צל רך מתחת למיקרופון (עומק) ----
shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sd = ImageDraw.Draw(shadow)
sd.rounded_rectangle([left, top, right, bottom], radius=cap_w / 2,
                     fill=(0, 30, 40, 150))
shadow = shadow.filter(ImageFilter.GaussianBlur(int(S * 0.018)))
icon = Image.alpha_composite(icon, shadow)

# ---- המיקרופון (לבן) + מעמד ----
mic = Image.new("RGBA", (S, S), (0, 0, 0, 0))
md = ImageDraw.Draw(mic)
md.rounded_rectangle([left, top, right, bottom], radius=cap_w / 2,
                     fill=(255, 255, 255, 255))
arc_bb = [cx - cap_w * 0.85, bottom - cap_w * 0.85,
          cx + cap_w * 0.85, bottom + cap_w * 0.55]
md.arc(arc_bb, start=15, end=165, fill=(255, 255, 255, 255), width=int(stroke))
leg_top = bottom + cap_w * 0.55
leg_bot = leg_top + S * 0.075
md.line([cx, leg_top, cx, leg_bot], fill=(255, 255, 255, 255), width=int(stroke))
md.line([cx - S * 0.085, leg_bot, cx + S * 0.085, leg_bot],
        fill=(255, 255, 255, 255), width=int(stroke))

# הברקה עליונה (גלוס) לתחושת עומק
gloss = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd = ImageDraw.Draw(gloss)
gd.ellipse([left + cap_w * 0.18, top + cap_h * 0.05,
            right - cap_w * 0.18, top + cap_h * 0.40],
           fill=(255, 255, 255, 80))
gloss = gloss.filter(ImageFilter.GaussianBlur(int(S * 0.012)))
mic = Image.alpha_composite(mic, gloss)
icon = Image.alpha_composite(icon, mic)

# ---- שמירה ----
icon.resize((256, 256), Image.LANCZOS).save("app.png")
sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
icon.resize((256, 256), Image.LANCZOS).save("app.ico", sizes=sizes)
print("saved app.png (256) + app.ico", [s[0] for s in sizes])
