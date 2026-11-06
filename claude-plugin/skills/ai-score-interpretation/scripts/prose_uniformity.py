#!/usr/bin/env python3
"""Explain which passages of a manuscript are likely to look machine-written to a detector.

This is a local DIAGNOSTIC, not an AI detector and not a copy of any vendor model.
It mimics one public fact: AI writing detectors only score long-form prose sentences
and skip headings, lists, tables, references and formulas. It then reports how uniform
each qualifying paragraph is, because very even sentence lengths, repeated sentence
openers and stock transition phrases are the patterns reviewers most often see in
flagged text.

Usage:  python -I prose_uniformity.py paper.docx [--top 10] [--json]
Supports .docx (python-docx), .txt, .md.

Part of AEGIS (https://github.com/sunilgentyala/aegis-integrity), created, designed and
developed by Sunil Gentyala. GNU AGPL-3.0-or-later, Copyright (c) 2026 Sunil Gentyala.
"""
import argparse
import json
import re
import statistics
import sys

ABBREV = ("et al.", "e.g.", "i.e.", "Fig.", "Figs.", "Eq.", "vs.", "No.", "Sec.", "Ref.", "approx.", "cf.")
STOCK = (
    "it is worth noting", "plays a crucial role", "plays a pivotal role", "in today's",
    "furthermore", "moreover", "in conclusion", "delve", "landscape", "leverag",
    "robust", "comprehensive", "notably", "this ensures", "paramount", "seamless",
    "it is important to note", "in the realm of", "underscore", "holistic", "multifaceted",
)
MIN_PARA_WORDS = 25
MIN_SENTENCES = 2


def read_paragraphs(path):
    if path.lower().endswith(".docx"):
        import docx
        d = docx.Document(path)
        out = []
        for p in d.paragraphs:
            style = (p.style.name or "").lower() if p.style is not None else ""
            out.append((p.text.strip(), style))
        return out
    text = open(path, encoding="utf-8", errors="replace").read()
    return [(t.strip(), "") for t in re.split(r"\n\s*\n", text)]


def split_sentences(text):
    protected = text
    for a in ABBREV:
        protected = protected.replace(a, a.replace(".", "\u2024"))
    protected = re.sub(r"(\d)\.(\d)", "\\1\u2024\\2", protected)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", protected)
    return [p.replace("\u2024", ".").strip() for p in parts if p.strip()]


def qualifying(paragraphs):
    """Keep running prose, drop headings, lists, references, short fragments."""
    keep, skipped, in_refs = [], {"heading": 0, "list_or_short": 0, "references": 0}, False
    for text, style in paragraphs:
        if not text:
            continue
        if re.fullmatch(r"(?i)\W*(references|bibliography)\W*", text):
            in_refs = True
            skipped["heading"] += 1
            continue
        if in_refs or re.match(r"^\[\d+\]", text):
            skipped["references"] += 1
            continue
        if "heading" in style or "title" in style or text.isupper():
            skipped["heading"] += 1
            continue
        words = len(text.split())
        sents = split_sentences(text)
        if words < MIN_PARA_WORDS or len(sents) < MIN_SENTENCES or not text.rstrip().endswith((".", "!", "?")):
            skipped["list_or_short"] += 1
            continue
        keep.append(text)
    return keep, skipped


def metrics(par):
    sents = split_sentences(par)
    lens = [len(s.split()) for s in sents]
    mean = statistics.mean(lens)
    cv = statistics.pstdev(lens) / mean if mean else 0.0
    openers = [re.sub(r"\W", "", s.split()[0]).lower() for s in sents if s.split()]
    rep = 1 - len(set(openers)) / len(openers) if openers else 0.0
    low = par.lower()
    stock = sum(low.count(k) for k in STOCK)
    words = re.findall(r"[A-Za-z']+", low)
    ttr = len(set(words)) / len(words) if words else 0.0
    dashes = par.count("\u2014") + par.count(" -- ")
    return {
        "sentences": len(sents), "words": len(par.split()), "mean_len": round(mean, 1),
        "len_cv": round(cv, 2), "opener_repeat": round(rep, 2),
        "stock_per_100w": round(100 * stock / max(1, len(par.split())), 2),
        "ttr": round(ttr, 2), "dashes": dashes,
    }


def uniformity_score(m):
    """0..1, higher means more uniform. Heuristic, for ranking paragraphs only."""
    s = 0.0
    s += max(0.0, 0.45 - m["len_cv"]) / 0.45 * 0.5
    s += min(1.0, m["opener_repeat"] / 0.4) * 0.2
    s += min(1.0, m["stock_per_100w"] / 1.5) * 0.2
    s += min(1.0, m["dashes"] / 3) * 0.1
    return round(s, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    paras = read_paragraphs(a.path)
    total_words = sum(len(t.split()) for t, _ in paras)
    keep, skipped = qualifying(paras)
    rows = []
    for p in keep:
        m = metrics(p)
        m["uniformity"] = uniformity_score(m)
        m["snippet"] = p[:110] + ("..." if len(p) > 110 else "")
        rows.append(m)
    q_words = sum(r["words"] for r in rows)
    report = {
        "file": a.path,
        "total_words": total_words,
        "qualifying_prose_words": q_words,
        "qualifying_share": round(q_words / total_words, 2) if total_words else 0,
        "qualifying_paragraphs": len(rows),
        "skipped": skipped,
        "meets_300_word_minimum": q_words >= 300,
        "mean_len_cv": round(statistics.mean(r["len_cv"] for r in rows), 2) if rows else None,
        "mean_uniformity": round(statistics.mean(r["uniformity"] for r in rows), 2) if rows else None,
        "most_uniform": sorted(rows, key=lambda r: r["uniformity"], reverse=True)[: a.top],
        "note": "Diagnostic only. Not an AI detector. Use with version history and citation checks.",
    }
    if a.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0
    print(f"{a.path}")
    print(f"words {total_words}, qualifying prose {q_words} ({report['qualifying_share']:.0%}) in {len(rows)} paragraphs")
    print(f"skipped: {skipped}")
    print(f"mean sentence-length variation (cv) {report['mean_len_cv']}, mean uniformity {report['mean_uniformity']}")
    print("most uniform paragraphs:")
    for r in report["most_uniform"]:
        print(f"  u={r['uniformity']} cv={r['len_cv']} openers={r['opener_repeat']} stock/100w={r['stock_per_100w']} | {r['snippet']}")
    print(report["note"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
