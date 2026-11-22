"""Render docs/demo/demo.gif from REAL `aegis analyze` output.

Runs the CLI on docs/demo/sample_paper.txt (a synthetic paper with two invented
DOIs), captures its output, and animates a terminal replay with Pillow.
Usage:  python docs/demo/make_demo_gif.py
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CMD = ("aegis analyze sample_paper.txt --no-ai --no-semantic "
       "--no-stylometric --no-self-plagiarism")
W, H, PAD, FS = 1100, 640, 24, 17
BG, FG, DIM = (30, 31, 41), (230, 230, 240), (140, 145, 170)
GREEN, RED, CYAN, YEL = (80, 250, 123), (255, 85, 85), (139, 233, 253), (241, 250, 140)

FONT_PATHS = [r"C:\Windows\Fonts\consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
font = next(ImageFont.truetype(p, FS) for p in FONT_PATHS if os.path.exists(p))
LH = FS + 6
COLS = (W - 2 * PAD) // int(font.getlength("M"))

env = dict(os.environ, PYTHONIOENCODING="utf-8", NO_COLOR="1", COLUMNS="78")
proc = subprocess.run(
    [sys.executable, "-m", "aegis"] + CMD.split()[1:],
    cwd=HERE, capture_output=True, text=True, encoding="utf-8", env=env, timeout=300,
)
raw = (proc.stdout + proc.stderr).replace("\r", "")
lines = []
for ln in raw.splitlines():
    if ln.startswith("Analyzing "):
        continue
    lines.append(ln)
# keep the part that matters on screen
lines = [ln for ln in lines if not ln.startswith("No corpus loaded")]
lines = lines[:20]


def colour(ln):
    if "hallucinated" in ln:
        return RED
    if "Overall Risk" in ln:
        return GREEN
    if ln.startswith("Flags"):
        return YEL
    if ln.strip().startswith(("Watermark", "Target-publisher", "Math", "Grammar")):
        return DIM
    return FG


def frame(prompt_text, shown_lines, cursor=True):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((PAD + i * 26, 12, PAD + i * 26 + 14, 26), fill=c)
    d.text((W // 2 - 90, 10), "AEGIS integrity check", font=font, fill=DIM)
    y = 46
    d.text((PAD, y), "$ ", font=font, fill=CYAN)
    d.text((PAD + font.getlength("$ "), y), prompt_text + ("_" if cursor else ""), font=font, fill=FG)
    y += LH + 4
    for ln in shown_lines:
        d.text((PAD, y), ln[:COLS], font=font, fill=colour(ln))
        y += LH
    return img


frames, durations = [], []
frames.append(frame("", [])); durations.append(500)
step = 3
for i in range(step, len(CMD) + step, step):
    frames.append(frame(CMD[:i], [])); durations.append(45)
frames.append(frame(CMD, [], cursor=False)); durations.append(600)
for n in range(1, len(lines) + 1):
    frames.append(frame(CMD, lines[:n], cursor=False)); durations.append(110)
frames.append(frames[-1]); durations.append(3500)

out = HERE / "demo.gif"
pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
pal[0].save(out, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True)
print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(frames)} frames)")
