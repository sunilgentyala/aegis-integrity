"""
Generates docs/thumbnail.png (1200x630) for AEGIS social sharing.
Run: python docs/make_thumbnail.py
Requires: pip install Pillow
"""
from PIL import Image, ImageDraw, ImageFont
import os, math

W, H = 1200, 630
OUT = os.path.join(os.path.dirname(__file__), "thumbnail.png")

# ── colour palette ──────────────────────────────────────────────
BG       = (13,  17,  23)
BG2      = (22,  27,  34)
BORDER   = (48,  54,  61)
BLUE     = (88,  166, 255)
GREEN    = (63,  185, 80)
PURPLE   = (210, 168, 255)
ORANGE   = (255, 166, 87)
RED      = (247, 129, 102)
TEXT     = (230, 237, 243)
MUTED    = (139, 148, 158)
DIM      = (110, 118, 125)

# ── font helpers ─────────────────────────────────────────────────
FONT_DIR = r"C:\Windows\Fonts"

def font(name, size):
    candidates = {
        "bold":  ["arialbd.ttf", "Arial Bold.ttf", "calibrib.ttf"],
        "black": ["ariblk.ttf",  "Arial Black.ttf","segoeuib.ttf"],
        "reg":   ["arial.ttf",   "segoeui.ttf",    "calibri.ttf"],
        "mono":  ["consola.ttf", "cour.ttf",       "lucon.ttf"],
    }
    for fname in candidates.get(name, candidates["reg"]):
        path = os.path.join(FONT_DIR, fname)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

# ── gradient helper ───────────────────────────────────────────────
def h_gradient(draw, x, y, w, h, c1, c2):
    for i in range(w):
        t = i / max(w - 1, 1)
        r = int(c1[0] + (c2[0]-c1[0])*t)
        g = int(c1[1] + (c2[1]-c1[1])*t)
        b = int(c1[2] + (c2[2]-c1[2])*t)
        draw.line([(x+i, y), (x+i, y+h)], fill=(r,g,b))

def v_gradient_rect(img, x, y, w, h, c1, c2, alpha=255):
    arr = img.load()
    for j in range(h):
        t = j / max(h-1, 1)
        r = int(c1[0]+(c2[0]-c1[0])*t)
        g = int(c1[1]+(c2[1]-c1[1])*t)
        b = int(c1[2]+(c2[2]-c1[2])*t)
        for i in range(w):
            if 0<=x+i<W and 0<=y+j<H:
                arr[x+i, y+j] = (r,g,b)

def circle_aa(draw, cx, cy, r, fill, outline=None, ow=1):
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=fill,
                 outline=outline, width=ow)

def rounded_rect(draw, x, y, w, h, r, fill=None, outline=None, ow=1):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=r,
                           fill=fill, outline=outline, width=ow)

def pill(draw, x, y, w, h, fill, outline, text, tf, tc):
    rounded_rect(draw, x, y, w, h, h//2, fill=fill, outline=outline)
    tw = draw.textlength(text, font=tf)
    draw.text((x+(w-tw)//2, y+(h - tf.size)//2 - 1), text, font=tf, fill=tc)

# ═══════════════════════════════════════════════════════════════════
img  = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

# ── dot grid ─────────────────────────────────────────────────────
for gx in range(30, W, 40):
    for gy in range(30, H, 40):
        draw.ellipse([gx-1,gy-1,gx+1,gy+1], fill=(88,166,255,18))

# ── ambient glow blobs (low-opacity ellipses) ─────────────────────
def glow_blob(cx, cy, rx, ry, color, alpha=12):
    blob = Image.new("RGB", (W, H), BG)
    bd   = ImageDraw.Draw(blob)
    bd.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=color)
    img.paste(Image.blend(img, blob, alpha/255), (0,0))

glow_blob(170, 315, 260, 200, (30, 60, 110))
glow_blob(880, 190, 210, 150, (20,  80,  35))
glow_blob(1060,500, 180, 130, ( 60, 40, 100))

# ── top accent bar (3-stop gradient: blue → green → purple) ──────
for i in range(W):
    t = i / (W-1)
    if t < 0.5:
        t2 = t*2
        c = tuple(int(BLUE[k]+(GREEN[k]-BLUE[k])*t2) for k in range(3))
    else:
        t2 = (t-0.5)*2
        c = tuple(int(GREEN[k]+(PURPLE[k]-GREEN[k])*t2) for k in range(3))
    draw.line([(i,0),(i,5)], fill=c)

# ══════════════ LEFT PANEL ════════════════════════════════════════

# ── shield ───────────────────────────────────────────────────────
SX, SY, SW, SH = 72, 68, 200, 240
cx = SX + SW//2

def shield_path(ox, oy, w, h):
    pts = []
    # top-left to top-right arc
    steps = 40
    # shield as polygon: top straight, sides curve in, bottom point
    hw = w//2
    for i in range(steps+1):
        angle = math.pi + (math.pi * i / steps)
        px = ox + hw + int(math.cos(angle)*hw*0.08)
        py = oy + int(i/steps * h * 0.55)
        pts.append((px, py))
    # bottom point
    pts.append((ox+hw, oy+h))
    # right side going up
    for i in range(steps, -1, -1):
        angle = math.pi + (math.pi * i / steps)
        px = ox + hw - int(math.cos(angle)*hw*0.08)
        py = oy + int(i/steps * h * 0.55)
        pts.append((px, py))
    return pts

# Simple shield: trapezoid top + triangle bottom
def draw_shield(cx, ty, w, h, fill, outline, ow=2):
    hw = w//2
    half_bottom = h * 0.62
    pts = [
        (cx-hw,    ty),          # top-left
        (cx+hw,    ty),          # top-right
        (cx+hw,    ty+half_bottom), # mid-right
        (cx,       ty+h),        # bottom point
        (cx-hw,    ty+half_bottom), # mid-left
    ]
    draw.polygon(pts, fill=fill, outline=outline)

# outer glow shield
draw_shield(cx, SY,    SW+20, SH+24, (30,50,80), None)
draw_shield(cx, SY+6,  SW,    SH,    (15,25,40), BLUE, 2)

# gradient fill sim (horizontal slices)
for row in range(SH-10):
    t   = row / (SH-10)
    col = tuple(int(BLUE[k]+(GREEN[k]-BLUE[k])*t) for k in range(3))
    alpha_factor = 0.15
    blend = tuple(int(BG[k]*(1-alpha_factor)+col[k]*alpha_factor) for k in range(3))
    hw  = SW//2 - 2
    bot_frac = 0.62
    if row/SH < bot_frac:
        draw.line([(cx-hw, SY+6+row),(cx+hw, SY+6+row)], fill=blend)
    else:
        taper = 1 - (row/SH - bot_frac) / (1-bot_frac)
        tw2   = int(hw * taper)
        if tw2 > 0:
            draw.line([(cx-tw2, SY+6+row),(cx+tw2, SY+6+row)], fill=blend)

draw_shield(cx, SY+6, SW, SH, None, BLUE, 2)

# Letter A inside shield
fA   = font("black", 88)
draw.text((cx, SY+90), "A", font=fA, fill=BLUE, anchor="mm")

# tick at shield bottom
ty2 = SY + SH - 30
draw.line([(cx-22, ty2),(cx-6, ty2+18),(cx+24, ty2-14)],
          fill=GREEN, width=5)

# ── AEGIS wordmark ────────────────────────────────────────────────
fWord = font("black", 88)
draw.text((72, 375), "AEGIS", font=fWord, fill=TEXT)

# underline gradient
wl = int(draw.textlength("AEGIS", font=fWord))
for i in range(wl):
    t = i/wl
    c = tuple(int(BLUE[k]+(GREEN[k]-BLUE[k])*t) for k in range(3))
    draw.rectangle([72+i, 388, 72+i+1, 393], fill=c)

# tagline
fTag = font("reg", 20)
draw.text((72, 410), "Open-Source Academic Integrity Engine", font=fTag, fill=MUTED)
fSub = font("reg", 16)
draw.text((72, 438), "Plagiarism · AI Detection · LLM Watermarks · Citation Integrity",
          font=fSub, fill=DIM)

# ── vertical divider ─────────────────────────────────────────────
draw.line([(468,55),(468,548)], fill=BORDER, width=1)

# ══════════════ RIGHT PANEL ═══════════════════════════════════════
RX = 498   # right panel x start

# ── live badge ──────────────────────────────────────────────────
pb_text = "v2.0.0  ·  MIT License  ·  100% Offline"
fBadge  = font("bold", 14)
pb_w    = int(draw.textlength(pb_text, font=fBadge)) + 46
rounded_rect(draw, RX, 60, pb_w, 34, 17,
             fill=(10,35,15), outline=(63,185,80,200))
circle_aa(draw, RX+20, 77, 6, GREEN)
draw.text((RX+34, 68), pb_text, font=fBadge, fill=GREEN)

# ── big stat ──────────────────────────────────────────────────────
fBig  = font("black", 78)
fUnit = font("bold",  18)
fNote = font("reg",   13)
draw.text((RX, 110), "10", font=fBig, fill=BLUE)
num_w = int(draw.textlength("10", font=fBig))
draw.text((RX+num_w+10, 128), "Detection", font=fUnit, fill=MUTED)
draw.text((RX+num_w+10, 152), "Modules",   font=fUnit, fill=MUTED)
draw.text((RX+num_w+10, 178), "No other tool covers all", font=fNote, fill=DIM)

# ── feature grid (4 rows × 2 cols) ───────────────────────────────
features = [
    (BLUE,   "Citation Hallucination",  "Crossref DOI verification",   RED,    "LLM Watermark",        "Kirchenbauer z-test"),
    (GREEN,  "ESL Bias Correction",     "15 language calibrations",     PURPLE, "Ghostwriting Detect",  "Burrows' Delta stylo."),
    (ORANGE, "Semantic Coherence",      "AI-polish detection",          GREEN,  "Batch / Essay Mill",   "Classroom-level scan"),
    (BLUE,   "SBERT Paraphrase",        "Dense semantic retrieval",     ORANGE, "Self-Plagiarism",      "COPE guidelines"),
]

fFeat  = font("bold", 16)
fFsub  = font("reg",  13)
col1x, col2x = RX, RX + 310
row0y = 220
row_h = 72

for i, (c1,t1,s1,c2,t2,s2) in enumerate(features):
    ry = row0y + i*row_h
    # col 1
    circle_aa(draw, col1x+7, ry+8, 5, c1)
    draw.text((col1x+20, ry), t1, font=fFeat, fill=TEXT)
    draw.text((col1x+20, ry+22), s1, font=fFsub, fill=DIM)
    # col 2
    circle_aa(draw, col2x+7, ry+8, 5, c2)
    draw.text((col2x+20, ry), t2, font=fFeat, fill=TEXT)
    draw.text((col2x+20, ry+22), s2, font=fFsub, fill=DIM)

# ══════════════ BOTTOM BAR ════════════════════════════════════════
draw.rectangle([0, 548, W, H], fill=BG2)
draw.line([(0,548),(W,548)], fill=BORDER, width=1)

fName  = font("bold", 17)
fCred  = font("reg",  13)
fUrl   = font("bold", 13)

draw.text((72, 572), "Sunil Gentyala", font=fName, fill=TEXT)
draw.text((72, 597), "IEEE Senior Member  ·  CISM  ·  ISACA  ·  HCL America Inc., Dallas TX",
          font=fCred, fill=MUTED)

# credential pills
pills = [
    ("IEEE Sr. Member", BLUE,   (10,20,40)),
    ("CISM",            GREEN,  (10,35,15)),
    ("ISACA",           PURPLE, (30,15,50)),
]
px = 420
for label, fc, bg in pills:
    fw    = int(draw.textlength(label, font=fCred)) + 20
    rounded_rect(draw, px, 567, fw, 26, 5, fill=bg, outline=fc)
    draw.text((px+fw//2, 572), label, font=fCred, fill=fc, anchor="mt")
    px += fw + 10

# URLs right-aligned
url1 = "github.com/sunilgentyala/aegis-integrity"
url2 = "sunilgentyala.github.io/aegis-integrity"
u1w  = int(draw.textlength(url1, font=fUrl))
u2w  = int(draw.textlength(url2, font=fFsub))
draw.text((W-40-u1w, 572), url1, font=fUrl,  fill=BLUE)
draw.text((W-40-u2w, 597), url2, font=fFsub, fill=DIM)

# bottom accent bar
for i in range(W):
    t = i / (W-1)
    if t < 0.5:
        t2 = t*2
        c  = tuple(int(BLUE[k]+(GREEN[k]-BLUE[k])*t2) for k in range(3))
    else:
        t2 = (t-0.5)*2
        c  = tuple(int(GREEN[k]+(PURPLE[k]-GREEN[k])*t2) for k in range(3))
    draw.line([(i,H-5),(i,H-1)], fill=c)

# ── save ─────────────────────────────────────────────────────────
img.save(OUT, "PNG", optimize=True)
print(f"Saved: {OUT}  ({W}x{H})")
