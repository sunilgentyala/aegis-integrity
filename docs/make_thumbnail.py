"""
Generates the AEGIS thumbnails.

  docs/thumbnail.png         1200x630  social sharing card (GitHub Pages og:image)
  docs/thumbnail-square.png   512x512  square listing image (Glama, directories)

Run: python docs/make_thumbnail.py
Requires: pip install Pillow

AEGIS, Copyright (c) 2026 Sunil Gentyala. GNU AGPL-3.0-or-later.
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(__file__)
VERSION = "v3.4.0"

BG = (13, 17, 23)
PANEL = (22, 27, 34)
BORDER = (48, 54, 61)
BLUE = (88, 166, 255)
GREEN = (63, 185, 80)
PURPLE = (210, 168, 255)
ORANGE = (255, 166, 87)
RED = (247, 129, 102)
TEXT = (230, 237, 243)
MUTED = (139, 148, 158)

FONT_DIR = r"C:\Windows\Fonts"


def font(bold, size):
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, n), size)
        except OSError:
            continue
    return ImageFont.load_default()


def shield(draw, cx, top, w, h, fill, outline, ow):
    x0, x1 = cx - w // 2, cx + w // 2
    pts = [(x0, top), (x1, top), (x1, top + int(h * 0.58)),
           (cx, top + h), (x0, top + int(h * 0.58))]
    draw.polygon(pts, fill=fill, outline=outline, width=ow)


def draw_mark(draw, cx, top, w, h):
    shield(draw, cx, top, w, h, (24, 38, 60), BLUE, max(3, w // 40))
    f = font(True, int(w * 0.62))
    draw.text((cx, top + int(h * 0.36)), "A", font=f, fill=BLUE, anchor="mm")
    k = w / 100.0
    cy = top + int(h * 0.66)
    draw.line([(cx - 16 * k, cy), (cx - 4 * k, cy + 12 * k), (cx + 18 * k, cy - 12 * k)],
              fill=GREEN, width=max(4, int(5 * k)), joint="curve")


def pill(draw, x, y, text, f, color):
    tw = draw.textlength(text, font=f)
    h = f.size + 14
    draw.rounded_rectangle([x, y, x + tw + 28, y + h], radius=h // 2,
                           fill=PANEL, outline=color, width=2)
    draw.text((x + 14, y + h // 2), text, font=f, fill=color, anchor="lm")
    return tw + 28


def dots(draw, w, h, step=36):
    for x in range(step // 2, w, step):
        for y in range(step // 2, h, step):
            draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(26, 40, 60))


def social():
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    dots(d, W, H)
    d.rectangle([0, 0, W, 5], fill=BLUE)
    d.rectangle([0, H - 5, W, H], fill=GREEN)

    draw_mark(d, 230, 62, 220, 252)
    d.text((72, 420), "AEGIS", font=font(True, 96), fill=TEXT, anchor="ls")
    d.rectangle([72, 440, 392, 446], fill=BLUE)
    d.text((72, 490), "Academic Integrity Engine", font=font(False, 30), fill=MUTED, anchor="ls")

    d.line([(470, 60), (470, 530)], fill=BORDER, width=2)
    x = 505
    x += pill(d, x, 62, VERSION, font(True, 20), GREEN) + 10
    x += pill(d, x, 62, "AGPL-3.0", font(True, 20), BLUE) + 10
    pill(d, x, 62, "100% Offline", font(True, 20), PURPLE)

    items = [
        ("Citation hallucination", "Crossref DOI verification", BLUE),
        ("LLM watermark", "Kirchenbauer z-test", RED),
        ("ESL bias correction", "15 language calibrations", GREEN),
        ("Ghostwriting detect", "Burrows' Delta stylometry", PURPLE),
        ("Semantic coherence", "AI-polish detection", ORANGE),
        ("Essay mill, batch scan", "Classroom-level scanning", GREEN),
        ("SBERT paraphrase", "Dense semantic retrieval", BLUE),
        ("Self-plagiarism", "Corpus comparison, COPE aware", ORANGE),
        ("Source-use skills", "Harvard and Stanford guidance", PURPLE),
    ]
    for i, (t, s, c) in enumerate(items):
        col, row = i % 2, i // 2
        px, py = 505 + col * 340, 140 + row * 82
        d.ellipse([px, py + 8, px + 14, py + 22], fill=c)
        d.text((px + 28, py + 15), t, font=font(True, 24), fill=TEXT, anchor="lm")
        d.text((px + 28, py + 46), s, font=font(False, 17), fill=MUTED, anchor="lm")

    d.rectangle([0, 550, W, H], fill=PANEL)
    d.text((72, 578), "Sunil Gentyala", font=font(True, 24), fill=TEXT, anchor="lm")
    d.text((72, 608), "Author, developer, architect and scientist  |  IEEE Senior Member",
           font=font(False, 17), fill=MUTED, anchor="lm")
    d.text((W - 60, 578), "github.com/sunilgentyala/aegis-integrity", font=font(True, 20),
           fill=BLUE, anchor="rm")
    d.text((W - 60, 608), "sunilgentyala.github.io/aegis-integrity", font=font(False, 17),
           fill=MUTED, anchor="rm")
    img.save(os.path.join(HERE, "thumbnail.png"), optimize=True)


def square():
    S = 512
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)
    dots(d, S, S, 32)
    d.rectangle([0, 0, S, 8], fill=BLUE)
    d.rectangle([0, S - 8, S, S], fill=GREEN)
    draw_mark(d, S // 2, 44, 230, 262)
    d.text((S // 2, 372), "AEGIS", font=font(True, 78), fill=TEXT, anchor="mm")
    d.text((S // 2, 424), "Academic Integrity Checker", font=font(False, 26), fill=MUTED, anchor="mm")
    d.text((S // 2, 470), "by Sunil Gentyala", font=font(True, 24), fill=BLUE, anchor="mm")
    img.save(os.path.join(HERE, "thumbnail-square.png"), optimize=True)


if __name__ == "__main__":
    social()
    square()
    print("wrote thumbnail.png and thumbnail-square.png")
