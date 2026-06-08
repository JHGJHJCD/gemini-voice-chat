#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_icon.py
------------
מייצר אייקון מותאם (app.ico) - מיקרופון מודרני על רקע גרדיאנט.
הרצה חד-פעמית:  python make_icon.py
"""

from PIL import Image, ImageDraw


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_icon(size: int) -> Image.Image:
    # על-דגימה (4x) לקצוות חלקים
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # --- רקע: ריבוע מעוגל עם גרדיאנט אנכי (ציאן כהה -> בהיר) ---
    top = (14, 70, 90)       # ציאן כהה
    bot = (38, 198, 218)     # ציאן בהיר (#26c6da)
    radius = int(S * 0.22)

    # ציור הגרדיאנט שורה-שורה לתוך מסכה מעוגלת
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(top, bot, y / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, S, S], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    # --- מיקרופון לבן במרכז ---
    white = (255, 255, 255, 255)
    cx = S // 2

    # גוף המיקרופון (קפסולה)
    mic_w = int(S * 0.26)
    mic_top = int(S * 0.20)
    mic_bot = int(S * 0.55)
    d.rounded_rectangle(
        [cx - mic_w // 2, mic_top, cx + mic_w // 2, mic_bot],
        radius=mic_w // 2, fill=white,
    )

    # קשת ההחזקה (חצי עיגול פתוח מתחת לקפסולה)
    arc_w = int(S * 0.40)
    arc_top = int(S * 0.34)
    arc_bot = int(S * 0.66)
    line_w = max(int(S * 0.035), 2)
    d.arc(
        [cx - arc_w // 2, arc_top, cx + arc_w // 2, arc_bot],
        start=20, end=160, fill=white, width=line_w,
    )

    # רגל המיקרופון
    stand_top = int(S * 0.66)
    stand_bot = int(S * 0.76)
    d.line([(cx, stand_top), (cx, stand_bot)], fill=white, width=line_w)

    # בסיס
    base_w = int(S * 0.22)
    base_y = int(S * 0.76)
    d.line(
        [(cx - base_w // 2, base_y), (cx + base_w // 2, base_y)],
        fill=white, width=line_w,
    )

    # הקטנה לגודל הסופי (אנטי-aliasing)
    return img.resize((size, size), Image.LANCZOS)


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [make_icon(s) for s in sizes]
    # שמירה כ-.ico עם כל הגדלים
    images[0].save(
        "app.ico", format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    # שמירה גם כ-PNG לתצוגה בממשק
    make_icon(256).save("app.png", format="PNG")
    print("[OK] נוצרו app.ico ו-app.png")


if __name__ == "__main__":
    main()
