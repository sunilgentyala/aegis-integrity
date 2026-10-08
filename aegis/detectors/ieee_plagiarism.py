"""
IEEE plagiarism-level classifier -- maps AEGIS similarity evidence onto the
levels defined in the IEEE PSPB Operations Manual (amended 25 June 2026),
Section 8.2.4.D "Guidelines for Adjudicating Different Levels of
Plagiarism", plus the reuse rules of 8.2.4.G and 8.2.10.

Levels (8.2.4.D):
  1  Plagiarism of a MAJOR portion (>= 50% of the work, verbatim or
     paraphrased, or the main contributions used without acknowledgment)
  2  Plagiarism of a LARGE portion (20% to 50%)
  3  Uncredited verbatim copying of individual elements (paragraphs,
     sentences, illustrations) amounting to a SIGNIFICANT portion (< 20%)
  4  Credited verbatim copying of a major portion WITHOUT clear
     delineation (a credit notice exists, but no quotation marks / offset
     text identifies exactly what was copied)

The manual states these percentages "generally characterize" the portions
and that the delineation "is determined in the adjudication process". This
module therefore reports an INDICATIVE level for the author's pre-submission
use. It is evidence for a human, never a misconduct finding.

Method: matched passages from the n-gram / semantic detectors are located in
the body text, merged into non-overlapping spans (so the same words are never
counted twice, and matches against several sources are summed as the manual
requires), and each span is tested for (a) an adjacent citation marker and
(b) quotation delineation.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

PSPB_EDITION = "IEEE PSPB Operations Manual, amended 25 June 2026 (260625)"

MAJOR_PCT = 50.0
LARGE_PCT = 20.0
_MERGE_GAP = 40   # chars; adjacent matched sentences form one passage

# Numeric IEEE markers [3], [3, 4], [3]-[5], [3]-[5], plus author-year forms.
_CITE_RE = re.compile(
    r"\[\s*\d+(?:\s*[,–—-]\s*\d+)*\s*\]"
    r"|\(\s*[A-Z][A-Za-z'\-]+(?: et al\.| and [A-Z][A-Za-z'\-]+)?,?\s+\d{4}[a-z]?\s*\)"
)
_OPEN_QUOTES = "\"“‘'"
_CLOSE_QUOTES = "\"”’'"

# Prior-work disclosure language (8.2.4.G author obligations, 8.2.10).
_DISCLOSURE_RE = re.compile(
    r"extended (?:version|paper)|extension of (?:our|the author|a)|"
    r"(?:preliminary|earlier|conference|workshop|short) version|"
    r"previously (?:presented|published|reported)|"
    r"portions? of (?:this|the) (?:work|paper|article) (?:were|was|have been|has been)|"
    r"(?:first|originally) (?:presented|appeared|published)|"
    r"building on (?:our|the authors') (?:earlier|previous|prior)|"
    r"(?:our|authors') (?:earlier|previous|prior) (?:work|paper|study)",
    re.I,
)

# A figure/table caption that says it was taken from elsewhere.
_CAPTION_RE = re.compile(
    r"^\s*(?:Fig(?:ure)?\.?|Table)\s*[IVXLC\d]+[.:]?[^\n]*", re.I | re.M)
_BORROW_RE = re.compile(
    r"adapted from|reproduced from|reprinted from|redrawn from|"
    r"taken from|courtesy of|source:|©|copyright", re.I)
_PERMISSION_RE = re.compile(
    r"permission|licen[sc]e|CC[ -]BY|creative commons|used with", re.I)


@dataclass
class IEEEPlagiarismPassage:
    source_label: str
    text: str
    start: int
    end: int
    words: int
    kind: str          # "uncredited_verbatim" | "credited_undelineated"
                       # | "credited_delineated"
    detector: str      # "ngram" | "semantic"


@dataclass
class IEEEPlagiarismResult:
    body_words: int
    uncredited_pct: float            # verbatim-class overlap, no citation
    credited_undelineated_pct: float
    credited_delineated_pct: float   # acceptable if quotation is proportionate
    paraphrase_uncredited_pct: float  # share of sentences; advisory only
    indicative_level: Optional[int]  # 1-4, or None
    level_label: str
    portion: str                     # "major" | "large" | "significant" | "none"
    sources_involved: int
    passages: list[IEEEPlagiarismPassage] = field(default_factory=list)
    reuse_findings: list[str] = field(default_factory=list)
    illustration_findings: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    risk_level: str = "LOW"          # LOW | MEDIUM | HIGH | CRITICAL
    guidance: str = ""
    basis: str = PSPB_EDITION


_LEVEL_LABELS = {
    1: "Level 1 - Plagiarism of a major portion (8.2.4.D.1)",
    2: "Level 2 - Plagiarism of a large portion (8.2.4.D.2)",
    3: "Level 3 - Uncredited verbatim copying of individual elements, "
       "significant portion (8.2.4.D.3)",
    4: "Level 4 - Credited verbatim copying without clear delineation "
       "(8.2.4.D.4)",
}
_LEVEL_RISK = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "MEDIUM"}


def _norm_map(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapsed lowercase text plus index map back to original."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        if ch.isspace() or ch == "­":
            if not prev_space:
                out.append(" ")
                idx.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            idx.append(i)
            prev_space = False
    return "".join(out), idx


def _locate(norm: str, idx: list[int], segment: str) -> Optional[tuple[int, int]]:
    seg = " ".join(segment.split()).lower().strip()
    if len(seg) < 20:
        return None
    pos = norm.find(seg)
    if pos < 0:
        # Matches are often a window inside a longer sentence; try its core.
        core = seg[: max(20, len(seg) // 2)]
        pos = norm.find(core)
        if pos < 0:
            return None
        seg = core
    end = pos + len(seg) - 1
    return idx[pos], idx[end] + 1


def _merge(spans: list[tuple[int, int, str, str]]):
    """Merge overlapping spans; keep first label/detector."""
    spans = sorted(spans)
    merged: list[list] = []
    for s, e, label, det in spans:
        if merged and s <= merged[-1][1] + _MERGE_GAP:
            merged[-1][1] = max(merged[-1][1], e)
            merged[-1][4].add(label)
        else:
            merged.append([s, e, label, det, {label}])
    return merged


def _paragraph_end(text: str, end: int) -> int:
    """Matches are windows inside a passage; credit usually sits at the end
    of the paragraph, so look that far (bounded) for a citation marker."""
    nxt = text.find("\n\n", end)
    return len(text) if nxt < 0 else nxt


def _has_citation(text: str, start: int, end: int) -> bool:
    stop = min(_paragraph_end(text, end), end + 600)
    window = text[max(0, start - 40): stop]
    return bool(_CITE_RE.search(window))


def _word_ngrams(text: str, n: int = 3) -> set:
    w = re.findall(r"\w+", text.lower())
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def _is_verbatim_pair(query: str, source: str, cosine: float) -> bool:
    """A semantic hit is a verbatim copy, not a paraphrase, when the words
    themselves overlap (cosine ~1.0 alone is also treated as verbatim)."""
    if cosine >= 0.985:
        return True
    a, b = _word_ngrams(query), _word_ngrams(source)
    return bool(a and b) and len(a & b) / len(a | b) >= 0.6


def _is_delineated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 4): start].strip()
    after = text[end: end + 4].strip()
    inside_quotes = bool(before) and before[-1] in _OPEN_QUOTES
    closed = bool(after) and after[0] in _CLOSE_QUOTES
    # Whole span wrapped in quotes, or the span itself carries paired quotes.
    span = text[start:end]
    paired = span.count("“") >= 1 and span.count("”") >= 1
    return (inside_quotes and closed) or paired


class IEEEPlagiarismClassifier:
    """Classify similarity evidence against IEEE PSPB 8.2.4.D levels."""

    def __init__(self, min_segment_words: int = 8):
        self.min_segment_words = min_segment_words

    # ------------------------------------------------------------------

    def analyze(
        self,
        body_text: str,
        ngram_matches: list,
        semantic_matches: list,
        self_plagiarism_result=None,
        full_text: Optional[str] = None,
        own_labels: Optional[set] = None,
    ) -> IEEEPlagiarismResult:
        """own_labels: corpus labels that are the authors' own prior works.
        Overlap with those is text recycling (8.2.4.G), reported by the
        self-plagiarism detector, so it is excluded from the plagiarism
        levels here to avoid counting it twice."""
        own = own_labels or set()
        ngram_matches = [m for m in ngram_matches or []
                         if m.source_label not in own]
        semantic_matches = [m for m in semantic_matches or []
                            if m.source_label not in own]
        norm, idx = _norm_map(body_text)
        body_words = max(1, len(body_text.split()))

        spans: list[tuple[int, int, str, str]] = []
        for m in ngram_matches or []:
            loc = _locate(norm, idx, m.query_segment)
            if loc:
                spans.append((loc[0], loc[1], m.source_label, "ngram"))
        para_spans: list[tuple[int, int, str, str]] = []
        for m in semantic_matches or []:
            loc = _locate(norm, idx, m.query_sentence)
            if not loc:
                continue
            verbatim = _is_verbatim_pair(
                m.query_sentence, m.source_sentence, m.cosine_score)
            (spans if verbatim or not m.is_paraphrase else para_spans).append(
                (loc[0], loc[1], m.source_label, "semantic"))

        passages: list[IEEEPlagiarismPassage] = []
        sources: set[str] = set()
        w_uncred = w_undelin = w_deline = 0
        for s, e, label, det, labels in _merge(spans):
            words = len(body_text[s:e].split())
            if words < self.min_segment_words:
                continue
            cited = _has_citation(body_text, s, e)
            delin = _is_delineated(body_text, s, e)
            if not cited:
                kind = "uncredited_verbatim"
                w_uncred += words
                sources |= labels
            elif not delin:
                kind = "credited_undelineated"
                w_undelin += words
                sources |= labels
            else:
                kind = "credited_delineated"
                w_deline += words
            passages.append(IEEEPlagiarismPassage(
                source_label=", ".join(sorted(labels)), text=body_text[s:e][:300],
                start=s, end=e, words=words, kind=kind, detector=det))

        # Semantic-only (paraphrase) matches: IEEE Level 1(b) covers use of
        # another's ideas/results without acknowledgment, but that needs a
        # human judgement, so it is reported as an advisory percentage only.
        para_sentences = 0
        for s, e, label, det, labels in _merge(para_spans):
            if len(body_text[s:e].split()) >= self.min_segment_words \
                    and not _has_citation(body_text, s, e):
                para_sentences += len(body_text[s:e].split())
        para_pct = round(100.0 * para_sentences / body_words, 2)

        uncred_pct = round(100.0 * w_uncred / body_words, 2)
        undelin_pct = round(100.0 * w_undelin / body_words, 2)
        deline_pct = round(100.0 * w_deline / body_words, 2)

        level, portion = self._level(uncred_pct, undelin_pct)

        reuse = self._reuse_findings(full_text or body_text, self_plagiarism_result)
        illus = self._illustration_findings(full_text or body_text)

        flags = self._flags(level, uncred_pct, undelin_pct, para_pct,
                            len(sources), reuse, illus)
        risk = _LEVEL_RISK.get(level, "LOW")
        if risk == "LOW" and (reuse or illus or undelin_pct >= LARGE_PCT):
            risk = "MEDIUM"

        return IEEEPlagiarismResult(
            body_words=body_words,
            uncredited_pct=uncred_pct,
            credited_undelineated_pct=undelin_pct,
            credited_delineated_pct=deline_pct,
            paraphrase_uncredited_pct=para_pct,
            indicative_level=level,
            level_label=_LEVEL_LABELS.get(level, "No IEEE plagiarism level indicated"),
            portion=portion,
            sources_involved=len(sources),
            passages=passages,
            reuse_findings=reuse,
            illustration_findings=illus,
            flags=flags,
            risk_level=risk,
            guidance=self._guidance(level),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _level(uncred: float, undelin: float) -> tuple[Optional[int], str]:
        # Uncredited material dominates; sums across sources count (8.2.4.D
        # Level 1/2 "sum of plagiarized material").
        if uncred >= MAJOR_PCT:
            return 1, "major"
        if uncred >= LARGE_PCT:
            return 2, "large"
        if uncred > 0:
            return 3, "significant"
        # Level 4 is defined for a MAJOR portion copied with credit but
        # without delineation; smaller amounts are an editorial fix, not a
        # level, but are still surfaced via flags.
        if undelin >= MAJOR_PCT:
            return 4, "major"
        return None, "none"

    @staticmethod
    def _reuse_findings(text: str, sp) -> list[str]:
        """8.2.4.G / 8.2.10: reuse of the authors' own prior work."""
        out: list[str] = []
        if sp is None or sp.overall_overlap_pct <= 0:
            return out
        disclosed = bool(_DISCLOSURE_RE.search(text))
        if sp.overall_overlap_pct > 15.0 and not disclosed:
            out.append(
                f"{sp.overall_overlap_pct:.1f}% overlap with the authors' prior "
                "work but no statement of the earlier version was found. "
                "IEEE 8.2.4.G requires authors to inform the editor of "
                "previous work and 8.2.10 requires citing it; add a "
                "footnote/acknowledgment and a reference to the earlier paper."
            )
        elif sp.overall_overlap_pct > 30.0:
            out.append(
                f"{sp.overall_overlap_pct:.1f}% overlap with prior work exceeds "
                "the range normally accepted for an extension; state the new "
                "contribution explicitly and tell the editor (8.2.4.G)."
            )
        return out

    @staticmethod
    def _illustration_findings(text: str) -> list[str]:
        """Illustrations are 'individual elements' under Level 3."""
        out: list[str] = []
        for m in _CAPTION_RE.finditer(text):
            cap = m.group(0)
            if _BORROW_RE.search(cap) and not _CITE_RE.search(cap):
                out.append(
                    f"Caption signals borrowed material without a reference: "
                    f"\"{cap.strip()[:90]}\""
                )
            elif _BORROW_RE.search(cap) and not _PERMISSION_RE.search(cap):
                # Cited, but IEEE expects permission/credit line for reuse.
                out.append(
                    f"Reused illustration is cited but carries no permission or "
                    f"licence note: \"{cap.strip()[:90]}\""
                )
        return out[:20]

    @staticmethod
    def _flags(level, uncred, undelin, para, nsources, reuse, illus) -> list[str]:
        flags: list[str] = []
        if level in (1, 2, 3):
            flags.append(
                f"[IEEE 8.2.4.D] Indicative {_LEVEL_LABELS[level].split(' - ')[0]}: "
                f"{uncred:.1f}% of body text matches {nsources} source(s) with no "
                "adjacent citation. Indicative only; levels are set by "
                "adjudication."
            )
        elif level == 4:
            flags.append(
                f"[IEEE 8.2.4.D] Indicative Level 4: {undelin:.1f}% of body text "
                "is copied verbatim with a citation but no quotation marks."
            )
        elif undelin > 0:
            near = (" This is approaching the Level 4 'major portion' "
                    "threshold (50%)." if undelin >= LARGE_PCT else
                    " (below the Level 4 'major portion' threshold)")
            flags.append(
                f"[IEEE 8.2.4.D] {undelin:.1f}% of body text is verbatim from a "
                "cited source without quotation marks; rewrite it or put it in "
                "quotation marks." + near
            )
        if para >= 10.0:
            flags.append(
                f"[IEEE 8.2.4.D.1(b)] {para:.1f}% of body text is a close "
                "paraphrase of corpus sources with no adjacent citation. If it "
                "carries their ideas, results or algorithms, attribute it."
            )
        flags.extend(f"[IEEE 8.2.4.G] {r}" for r in reuse)
        flags.extend(f"[IEEE 8.2.4.D.3] {i}" for i in illus)
        return flags

    @staticmethod
    def _guidance(level: Optional[int]) -> str:
        if level is None:
            return ("No IEEE plagiarism level indicated by the supplied corpus. "
                    "This is only as complete as the comparison corpus; it is "
                    "not a clearance.")
        return {
            1: "Remove or rewrite and cite every flagged passage before "
               "submission. Level 1 findings carry the harshest IEEE "
               "corrective actions (post-publication notice, up to five-year "
               "publication prohibition).",
            2: "Rewrite in your own words, quote verbatim text with quotation "
               "marks, and cite each source (8.2.4.D.2).",
            3: "Add quotation marks or offset text plus a reference for each "
               "verbatim passage, or rewrite it (8.2.4.D.3).",
            4: "Add quotation marks or block-quote formatting so the copied "
               "text is clearly delineated, or paraphrase it (8.2.4.D.4).",
        }[level]
