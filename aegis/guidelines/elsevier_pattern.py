"""
Elsevier / Information Fusion writing-pattern checks.

The numbers below were measured on two papers published in Information Fusion 139 (2027):
  * Ye & Wang, "Domain-adversarial anatomical graph networks for cross-user human activity
    recognition", 18 pages, 49 references (a methods paper).
  * Del Ser et al., "From assistants to auditors" (GRAAF), 44 pages, 192 references (a framework
    paper with an experimental validation).
Measured on both: mean sentence length 21.0 and 21.9 words (medians 19 and 21); 0 em dashes and
0 en dashes in running text; 0.8 and 0.2 occurrences of "However," per 1,000 words; contrastive
and additive sentence openers (However/Moreover/Furthermore/Additionally/Notably/In contrast/
Therefore/Thus/Specifically) 1.8 and 0.6 per 1,000 words; first-person plural ("we", "our") used
for the authors' own work; a numbered Introduction ending with a roadmap sentence; Related work
before Method; a limitations discussion; declarations in the order CRediT authorship contribution
statement, Declaration of competing interest, Data availability, then References; numbered
references listed in order of first citation.

Every check returns (rule, status, detail). Status is PASS, NEEDS_REVIEW or NOT_ENOUGH_DATA, as in
GuidelineComplianceChecker. These are pattern checks against two reference papers and the Guide for
Authors, not a judgement of scientific quality, and a NEEDS_REVIEW is a prompt to look, not a fault.
"""

from __future__ import annotations
import re
import statistics

# Measured reference bands (see module docstring).
SENTENCE_MEAN_BAND = (15.0, 28.0)
TRANSITION_PER_1000_MAX = 4.0
STOCK_PHRASE_PER_1000_MAX = 1.5
ABSTRACT_WORDS_MAX = 250

_TRANSITIONS = re.compile(
    r"(?:^|(?<=[.!?]\s))(?:However|Moreover|Furthermore|Additionally|Notably|In contrast|Therefore|"
    r"Thus|Specifically|Importantly|Crucially|Consequently|Overall|Indeed|In addition|Nevertheless),",
    re.MULTILINE)
_STOCK = re.compile(
    r"\b(?:delve[sd]?|tapestry|in the realm of|it is worth noting|it(?:'s| is) important to note|"
    r"ever-evolving|ever-changing|rapidly evolving landscape|testament to|underscor(?:e|es|ed|ing)|"
    r"seamless(?:ly)?|cutting-edge|game-chang\w+|paradigm shift|plays? a (?:crucial|pivotal|vital) role|"
    r"in today's|a myriad of|multifaceted|holistic)\b", re.IGNORECASE)
_ROADMAP = re.compile(
    r"(?:organi[sz]ed as follows|remainder of (?:this|the) (?:paper|article)|rest of (?:this|the) "
    r"(?:paper|article)|(?:paper|article) is (?:structured|organi[sz]ed)|Section\s+2\s+(?:reviews|presents|"
    r"provides|describes|surveys))", re.IGNORECASE)
_HEADING = re.compile(r"^\s*(\d+(?:\.\d+){0,3})\.?\s+([A-Z][^\n]{2,90})$", re.MULTILINE)
_CITE = re.compile(r"\[([1-9]\d*(?:\s*[,–-]\s*[1-9]\d*)*)\]")  # [0,1] is interval notation, not a citation
_REF_ENTRY = re.compile(r"^\s*\[(\d+)\]\s+\S", re.MULTILINE)
_GENAI = re.compile(r"declaration\s+of\s+generative\s+AI|generative\s+AI\s+and\s+AI-assisted|"
                    r"AI-assisted\s+technologies\s+in\s+the\s+(?:writing|manuscript)", re.IGNORECASE)
_DECL = {
    "credit": re.compile(r"credit\s+authorship\s+contribution\s+statement", re.IGNORECASE),
    "competing": re.compile(r"declaration\s+of\s+competing\s+interests?", re.IGNORECASE),
    "genai": _GENAI,
    "data": re.compile(r"^\s*data\s+availability(?:\s+statement)?\s*$", re.IGNORECASE | re.MULTILINE),
}


def _split_references(text: str):
    """Return (body, references_block). The last heading-only 'References' line starts the list."""
    matches = list(re.finditer(r"^\s*references\s*$", text, re.IGNORECASE | re.MULTILINE))
    if not matches:
        return text, ""
    start = matches[-1].start()
    return text[:start], text[start:]


def _abstract(text: str):
    m = re.search(r"^\s*abstract\s*:?\s*$|^\s*abstract\b[\s:.–-]", text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    rest = text[m.end():]
    stop = re.search(r"^\s*(?:keywords?\b|1\.?\s+introduction\b|highlights\b)", rest, re.IGNORECASE | re.MULTILINE)
    return (rest[:stop.start()] if stop else rest[:3000]).strip()


def _sentences(body: str):
    flat = re.sub(r"\s+", " ", body)
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", flat) if 5 <= len(s.split()) <= 90]


def _expand(group: str):
    out = []
    for part in re.split(r"\s*,\s*", group):
        span = re.split(r"\s*[–-]\s*", part)
        if len(span) == 2 and span[0].isdigit() and span[1].isdigit() and int(span[1]) >= int(span[0]):
            out.extend(range(int(span[0]), int(span[1]) + 1))
        elif part.strip().isdigit():
            out.append(int(part))
    return out


def run_checks(full_text: str):
    text = full_text or ""
    body, refs = _split_references(text)
    words = max(len(body.split()), 1)
    results = []

    # 1. Dashes: the reference papers contain none in running text.
    dashes = body.count("—") + len(re.findall(r"(?<!\d)–(?!\d)", body)) + body.count(" -- ")
    results.append(("No em or en dashes in running text",
                    "PASS" if dashes == 0 else "NEEDS_REVIEW",
                    "None found (both reference papers use none)." if dashes == 0 else
                    f"{dashes} em dash, spaced en dash or double-hyphen mark(s); the reference papers use none."))

    # 2. Sentence length.
    sents = _sentences(body)
    if len(sents) >= 30:
        lens = [len(s.split()) for s in sents]
        mean, med = statistics.mean(lens), statistics.median(lens)
        long_share = sum(1 for n in lens if n > 40) / len(lens)
        ok = SENTENCE_MEAN_BAND[0] <= mean <= SENTENCE_MEAN_BAND[1] and long_share < 0.10
        results.append(("Sentence length close to the published papers",
                        "PASS" if ok else "NEEDS_REVIEW",
                        f"Mean {mean:.1f} words (median {med:.0f}); {100 * long_share:.1f}% over 40 words. "
                        f"Reference papers: mean 21.0 and 21.9, median 19 and 21; over 40 words 6.6% and 7.6% (PDF text, limit used 10%)."))
    else:
        results.append(("Sentence length close to the published papers", "NOT_ENOUGH_DATA",
                        "Too few sentences recovered from the text."))

    # 3. Transition openers.
    t = len(_TRANSITIONS.findall(body)) * 1000 / words
    results.append(("Sentence-opening transitions at published density",
                    "PASS" if t <= TRANSITION_PER_1000_MAX else "NEEDS_REVIEW",
                    f"{t:.1f} per 1,000 words (reference papers: 1.8 and 0.6; limit used {TRANSITION_PER_1000_MAX})."))

    # 4. Stock phrases.
    s = len(_STOCK.findall(body)) * 1000 / words
    results.append(("Stock promotional or filler phrases",
                    "PASS" if s <= STOCK_PHRASE_PER_1000_MAX else "NEEDS_REVIEW",
                    f"{s:.1f} per 1,000 words (limit used {STOCK_PHRASE_PER_1000_MAX})."))

    # 5. Abstract length.
    ab = _abstract(text)
    if ab is None:
        results.append(("Abstract within 250 words", "NOT_ENOUGH_DATA", "No Abstract heading found."))
    else:
        n = len(ab.split())
        results.append(("Abstract within 250 words", "PASS" if 60 <= n <= ABSTRACT_WORDS_MAX else "NEEDS_REVIEW",
                        f"{n} words (Information Fusion Guide for Authors: at most {ABSTRACT_WORDS_MAX})."))
        cited = bool(_CITE.search(ab))
        results.append(("Abstract free of citations", "PASS" if not cited else "NEEDS_REVIEW",
                        "No bracketed citations in the abstract." if not cited else
                        "The abstract contains bracketed citations."))

    # 6. Keywords.
    km = re.search(r"^\s*keywords?\s*:?\s*(.*)$", text, re.IGNORECASE | re.MULTILINE)
    if km:
        same_line = km.group(1).strip()
        if same_line:
            blob = same_line
        else:
            nxt = text[km.end():km.end() + 400].split("\n")
            kept = []
            for x in nxt:
                if not x.strip():
                    if kept:
                        break
                    continue
                if re.match(r"\s*\d+\.?\s+[A-Z]", x):
                    break
                kept.append(x)
            blob = " ".join(kept)
        items = [k for k in re.split(r"[;,\n]", blob) if k.strip()]
        results.append(("1 to 7 keywords", "PASS" if 1 <= len(items) <= 7 else "NEEDS_REVIEW",
                        f"{len(items)} keyword(s) found."))
    else:
        results.append(("1 to 7 keywords", "NOT_ENOUGH_DATA", "No Keywords line found."))

    # 7. Numbered section skeleton.
    heads = [(m.group(1), m.group(2).strip()) for m in _HEADING.finditer(body)]
    tops = [(n, h) for n, h in heads if "." not in n]
    names = [h.lower() for _, h in tops]
    if tops:
        has_intro = names[0].startswith("introduction")
        has_related = any("related" in h or "background" in h or "literature" in h for h in names)
        has_concl = any(h.startswith("conclusion") for h in names)
        nums = [int(n) for n, _ in tops]
        consecutive = nums == list(range(1, len(nums) + 1)) or nums[:1] == [1]
        missing = [lab for lab, ok in (("Introduction first", has_intro), ("a Related work section", has_related),
                                        ("Conclusion(s)", has_concl), ("consecutive numbering", consecutive)) if not ok]
        results.append(("Numbered section skeleton (Introduction, Related work, ..., Conclusion)",
                        "PASS" if not missing else "NEEDS_REVIEW",
                        f"{len(tops)} numbered top-level sections." if not missing else
                        "Missing or off-pattern: " + ", ".join(missing) + "."))
    else:
        results.append(("Numbered section skeleton (Introduction, Related work, ..., Conclusion)",
                        "NOT_ENOUGH_DATA", "No numbered headings recognised."))

    # 8. Roadmap and contributions in the Introduction.
    im = re.search(r"^\s*1\.?\s+introduction\s*$", body, re.IGNORECASE | re.MULTILINE)
    if im:
        nm = re.search(r"^\s*2\.?\s+[A-Z]", body[im.end():], re.MULTILINE)
        intro = body[im.end():im.end() + (nm.start() if nm else 12000)]
        results.append(("Introduction ends with a roadmap sentence", "PASS" if _ROADMAP.search(intro) else "NEEDS_REVIEW",
                        "Roadmap sentence found." if _ROADMAP.search(intro) else
                        'No "organized as follows" style roadmap found in the Introduction.'))
        has_contrib = bool(re.search(r"contribution", intro, re.IGNORECASE))
        results.append(("Introduction states the contributions", "PASS" if has_contrib else "NEEDS_REVIEW",
                        "Contributions are stated." if has_contrib else "The Introduction does not mention contributions."))
    else:
        results.append(("Introduction roadmap and contributions", "NOT_ENOUGH_DATA", "No numbered Introduction found."))

    # 9. Limitations.
    lim = len(re.findall(r"limitation", body, re.IGNORECASE))
    results.append(("Limitations discussed", "PASS" if lim >= 2 else "NEEDS_REVIEW",
                    f'"limitation" appears {lim} time(s); the reference papers use it 10 and 32 times.'))

    # 10. Declarations present and in the published order.
    pos = {k: (m.start() if (m := rx.search(text)) else -1) for k, rx in _DECL.items()}
    present = [k for k in ("credit", "competing", "genai", "data") if pos[k] >= 0]
    missing = [k for k in ("credit", "competing", "genai", "data") if pos[k] < 0]
    ordered = [pos[k] for k in present] == sorted(pos[k] for k in present)
    label = {"credit": "CRediT", "competing": "competing interest", "genai": "generative-AI declaration",
             "data": "Data availability"}
    detail = ("All four declarations present" if not missing else "Missing: " + ", ".join(label[k] for k in missing)) + \
             ("; order matches the published pattern." if ordered else "; order differs from the published pattern "
              "(CRediT, competing interest, generative AI, data availability).")
    results.append(("Declarations present and ordered like the published papers",
                    "PASS" if not missing and ordered else "NEEDS_REVIEW", detail))
    pms = list(re.finditer(r"^\s*references\s*$", text, re.IGNORECASE | re.MULTILINE))
    if present and pms:
        after = max(pos[k] for k in present) < pms[-1].start()
        results.append(("Declarations sit before the reference list", "PASS" if after else "NEEDS_REVIEW",
                        "Declarations precede References." if after else "A declaration appears after the reference list."))

    # 11. Corresponding author line.
    results.append(("Corresponding author identified",
                    "PASS" if re.search(r"corresponding\s+author", text, re.IGNORECASE) else "NEEDS_REVIEW",
                    "Corresponding author line found." if re.search(r"corresponding\s+author", text, re.IGNORECASE)
                    else "No corresponding author line found."))

    # 12. Numbered references: contiguous, cited, in order of first citation.
    entries = [int(x) for x in _REF_ENTRY.findall(refs)]
    if entries:
        contiguous = entries == list(range(1, len(entries) + 1))
        top, order_ok, cited_nums = 0, True, set()
        for m in _CITE.finditer(body):
            for n in _expand(m.group(1)):
                if n not in cited_nums and n != top + 1:
                    order_ok = False
                cited_nums.add(n)
                top = max(top, n)
        uncited = sorted(set(entries) - cited_nums)
        unresolved = sorted(n for n in cited_nums if n not in set(entries))
        problems = []
        if not contiguous:
            problems.append("reference numbers are not contiguous from [1]")
        if not order_ok:
            problems.append("references are not numbered in order of first citation")
        if uncited:
            problems.append(f"uncited entries: {uncited[:8]}")
        if unresolved:
            problems.append(f"citations with no entry: {unresolved[:8]}")
        results.append(("Numbered references by first citation, all cited, all resolved",
                        "PASS" if not problems else "NEEDS_REVIEW",
                        f"{len(entries)} entries, {len(cited_nums)} distinct citations." if not problems else
                        "; ".join(problems) + "."))
        years = sum(1 for e in re.split(r"\n\s*\[\d+\]\s+", refs) if re.search(r"\((?:19|20)\d{2}\)", e))
        results.append(("Elsevier reference format (Initials Surname, Title, Journal vol (year) pages)",
                        "PASS" if years >= 0.9 * len(entries) else "NEEDS_REVIEW",
                        f"{years} of {len(entries)} entries carry a parenthesised year."))
    else:
        results.append(("Numbered references by first citation, all cited, all resolved", "NOT_ENOUGH_DATA",
                        "No bracket-numbered reference list recognised."))
    return results
