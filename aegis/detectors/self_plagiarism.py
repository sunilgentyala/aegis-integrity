"""
Self-Plagiarism / Text Recycling Detector -- AEGIS Novel Feature #4.

Critical gap: Turnitin's self-plagiarism check is locked behind ScholarOne
submissions. No open-source tool provides this for individual authors.

Two detection modes:
  1. Corpus mode: user supplies prior publications as a FAISS-indexed
     corpus; the submission is compared sentence-by-sentence via SBERT.
  2. Pairwise mode: direct comparison of two documents (e.g., a conference
     draft vs. the extended journal version).

Threshold guidance follows the Elsevier and COPE text recycling norms:
  - <= 15% verbatim overlap with prior own work: generally acceptable
    (methods, standard definitions)
  - 15-30%: requires disclosure and citation
  - > 30%: high risk of editorial rejection; editor notification required

Detection layers:
  - Character 5-gram Jaccard (fast, exact; catches copy-paste)
  - Word 3-gram Jaccard (catches minor rewording)
  - SBERT sentence cosine (catches paraphrase/translation recycling)
  - Highlighted passage list for human reviewer
"""

from __future__ import annotations
import re
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RecycledPassage:
    source_label: str          # prior publication identifier
    submission_text: str       # passage from current submission
    source_text: str           # matching passage from prior work
    char_jaccard: float        # character 5-gram overlap
    word_jaccard: float        # word 3-gram overlap
    semantic_score: float      # SBERT cosine (0 if SBERT not available)
    overlap_type: str          # "verbatim" | "near_verbatim" | "paraphrase"
    risk_level: str            # "LOW" | "MEDIUM" | "HIGH"


@dataclass
class SelfPlagiarismResult:
    overall_overlap_pct: float          # estimated % of submission recycled
    risk_level: str                     # LOW | MEDIUM | HIGH | CRITICAL
    recycled_passages: list[RecycledPassage]
    source_breakdown: dict[str, float]  # source_label -> overlap_pct
    flags: list[str]
    cope_guidance: str                  # human-readable recommendation


class SelfPlagiarismDetector:
    """
    Detect text recycling between a submission and an author's prior works.

    Combines fast n-gram overlap with optional SBERT semantic similarity
    so it catches both verbatim copy and paraphrase recycling.
    """

    CHAR_N = 5
    WORD_N = 3

    def __init__(
        self,
        char_threshold: float = 0.35,     # char Jaccard for verbatim match
        word_threshold: float = 0.25,     # word Jaccard for near-verbatim
        semantic_threshold: float = 0.88, # SBERT cosine for paraphrase
        medium_risk_pct: float = 15.0,    # % overlap triggers MEDIUM
        high_risk_pct: float = 30.0,      # % overlap triggers HIGH
        use_sbert: bool = True,
        device: str = "cpu",
    ):
        self.char_thresh = char_threshold
        self.word_thresh = word_threshold
        self.sem_thresh = semantic_threshold
        self.medium_pct = medium_risk_pct
        self.high_pct = high_risk_pct
        self.use_sbert = use_sbert
        self.device = device
        self._sbert = None
        self._corpus_index: list[tuple[str, str, str]] = []  # (label, para, sent)

    # ------------------------------------------------------------------
    # Corpus-mode API
    # ------------------------------------------------------------------

    def load_prior_works(self, corpus: list[tuple[str, str]]) -> None:
        """
        corpus: list of (label, full_text) for each prior publication.
        Stores sentence-level representations for semantic search.
        """
        self._corpus_index = []
        for label, text in corpus:
            paras = self._split_paragraphs(text)
            for para in paras:
                for sent in self._split_sentences(para):
                    if len(sent.split()) >= 8:
                        self._corpus_index.append((label, para, sent))

        if self.use_sbert and self._corpus_index:
            self._build_sbert_index()

    def _build_sbert_index(self):
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
            self._sbert = SentenceTransformer(
                "paraphrase-MiniLM-L6-v2", device=self.device)
            sents = [row[2] for row in self._corpus_index]
            vecs = self._sbert.encode(sents, batch_size=64,
                                      normalize_embeddings=True,
                                      show_progress_bar=False)
            dim = vecs.shape[1]
            self._faiss_index = faiss.IndexFlatIP(dim)
            self._faiss_index.add(vecs.astype("float32"))
        except ImportError:
            self._sbert = None
            self._faiss_index = None

    def check_submission(self, submission_text: str) -> SelfPlagiarismResult:
        """
        Compare submission against loaded prior works corpus.
        """
        sub_paras = self._split_paragraphs(submission_text)
        sub_sents = [s for p in sub_paras
                     for s in self._split_sentences(p) if len(s.split()) >= 8]

        if not self._corpus_index:
            return self._empty_result("No prior works loaded")

        passages: list[RecycledPassage] = []
        flagged_sub_sents: set[int] = set()

        # --- N-gram pass (fast, no ML) ---
        for si, sub_sent in enumerate(sub_sents):
            best: Optional[RecycledPassage] = None
            best_score = 0.0
            for label, para, corp_sent in self._corpus_index:
                cj = self._char_jaccard(sub_sent, corp_sent)
                wj = self._word_jaccard(sub_sent, corp_sent)
                combined = max(cj, wj)
                if combined < self.word_thresh:
                    continue
                if combined > best_score:
                    best_score = combined
                    otype = ("verbatim" if cj >= self.char_thresh
                             else "near_verbatim")
                    best = RecycledPassage(
                        source_label=label,
                        submission_text=sub_sent,
                        source_text=corp_sent,
                        char_jaccard=round(cj, 3),
                        word_jaccard=round(wj, 3),
                        semantic_score=0.0,
                        overlap_type=otype,
                        risk_level="HIGH" if cj >= self.char_thresh else "MEDIUM",
                    )
            if best:
                passages.append(best)
                flagged_sub_sents.add(si)

        # --- SBERT semantic pass (paraphrase recycling) ---
        if self._sbert is not None and hasattr(self, "_faiss_index"):
            unflagged = [s for i, s in enumerate(sub_sents)
                         if i not in flagged_sub_sents and len(s.split()) >= 10]
            if unflagged:
                import numpy as np
                q_vecs = self._sbert.encode(
                    unflagged, batch_size=32,
                    normalize_embeddings=True, show_progress_bar=False)
                scores, idxs = self._faiss_index.search(
                    q_vecs.astype("float32"), 1)
                for qi, (score_row, idx_row) in enumerate(zip(scores, idxs)):
                    score = float(score_row[0])
                    idx = int(idx_row[0])
                    if idx < 0 or score < self.sem_thresh:
                        continue
                    label, _, corp_sent = self._corpus_index[idx]
                    cj = self._char_jaccard(unflagged[qi], corp_sent)
                    wj = self._word_jaccard(unflagged[qi], corp_sent)
                    passages.append(RecycledPassage(
                        source_label=label,
                        submission_text=unflagged[qi],
                        source_text=corp_sent,
                        char_jaccard=round(cj, 3),
                        word_jaccard=round(wj, 3),
                        semantic_score=round(score, 3),
                        overlap_type="paraphrase",
                        risk_level="MEDIUM",
                    ))

        # --- Aggregate ---
        total_sents = max(len(sub_sents), 1)
        flagged_count = len({p.submission_text for p in passages})
        overlap_pct = round(100.0 * flagged_count / total_sents, 1)

        source_breakdown: dict[str, float] = {}
        for p in passages:
            source_breakdown[p.source_label] = source_breakdown.get(
                p.source_label, 0) + 1
        source_breakdown = {
            k: round(100.0 * v / total_sents, 1)
            for k, v in source_breakdown.items()
        }

        risk, cope = self._risk_and_cope(overlap_pct, passages)
        flags = self._build_flags(passages, overlap_pct)

        return SelfPlagiarismResult(
            overall_overlap_pct=overlap_pct,
            risk_level=risk,
            recycled_passages=passages,
            source_breakdown=source_breakdown,
            flags=flags,
            cope_guidance=cope,
        )

    # ------------------------------------------------------------------
    # Pairwise comparison (no corpus index needed)
    # ------------------------------------------------------------------

    def compare_documents(
        self, text_a: str, label_a: str,
        text_b: str, label_b: str,
    ) -> SelfPlagiarismResult:
        """
        Direct pairwise comparison: conference paper vs. journal extension.
        """
        sents_a = [s for s in self._split_sentences(text_a)
                   if len(s.split()) >= 8]
        sents_b = [s for s in self._split_sentences(text_b)
                   if len(s.split()) >= 8]

        passages: list[RecycledPassage] = []
        flagged_a: set[int] = set()

        for ia, sa in enumerate(sents_a):
            best_score = 0.0
            best_match: Optional[tuple] = None
            for sb in sents_b:
                cj = self._char_jaccard(sa, sb)
                wj = self._word_jaccard(sa, sb)
                score = max(cj, wj)
                if score > best_score and score >= self.word_thresh:
                    best_score = score
                    best_match = (sb, cj, wj)
            if best_match:
                sb, cj, wj = best_match
                otype = "verbatim" if cj >= self.char_thresh else "near_verbatim"
                passages.append(RecycledPassage(
                    source_label=label_b,
                    submission_text=sa,
                    source_text=sb,
                    char_jaccard=round(cj, 3),
                    word_jaccard=round(wj, 3),
                    semantic_score=0.0,
                    overlap_type=otype,
                    risk_level="HIGH" if cj >= self.char_thresh else "MEDIUM",
                ))
                flagged_a.add(ia)

        total = max(len(sents_a), 1)
        overlap_pct = round(100.0 * len(flagged_a) / total, 1)
        risk, cope = self._risk_and_cope(overlap_pct, passages)
        flags = self._build_flags(passages, overlap_pct)

        return SelfPlagiarismResult(
            overall_overlap_pct=overlap_pct,
            risk_level=risk,
            recycled_passages=passages,
            source_breakdown={label_b: overlap_pct},
            flags=flags,
            cope_guidance=cope,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _char_jaccard(self, a: str, b: str) -> float:
        sa = self._char_shingles(a)
        sb = self._char_shingles(b)
        if not sa and not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _word_jaccard(self, a: str, b: str) -> float:
        sa = self._word_shingles(a)
        sb = self._word_shingles(b)
        if not sa and not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _char_shingles(self, text: str) -> set[str]:
        t = re.sub(r"\s+", " ", text.lower())
        return {t[i:i + self.CHAR_N] for i in range(len(t) - self.CHAR_N + 1)}

    def _word_shingles(self, text: str) -> set[str]:
        tokens = re.findall(r"\b[a-z]{2,}\b", text.lower())
        return {" ".join(tokens[i:i + self.WORD_N])
                for i in range(len(tokens) - self.WORD_N + 1)}

    def _split_sentences(self, text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_paragraphs(self, text: str) -> list[str]:
        paras = re.split(r"\n\n+", text)
        return [p.strip() for p in paras if len(p.strip().split()) >= 15]

    def _risk_and_cope(
        self, pct: float, passages: list[RecycledPassage]
    ) -> tuple[str, str]:
        verbatim_count = sum(1 for p in passages if p.overlap_type == "verbatim")
        if pct > self.high_pct or verbatim_count > 5:
            return (
                "CRITICAL",
                "Overlap exceeds 30% or contains extensive verbatim copying. "
                "Per COPE guidelines this requires immediate disclosure to editors. "
                "Significant portions must be rewritten or removed before submission.",
            )
        if pct > self.medium_pct:
            return (
                "HIGH",
                "Overlap 15-30%. COPE and most publishers require explicit "
                "citation of prior own work and a statement in the cover letter "
                "disclosing overlap. Methods sections are partially exempt.",
            )
        if pct > 5.0:
            return (
                "MEDIUM",
                "Overlap 5-15%. Standard methods boilerplate and definitions "
                "are generally acceptable. Ensure all reused text is cited. "
                "Consider adding a brief disclosure in the cover letter.",
            )
        return (
            "LOW",
            "Overlap below 5%. This is within normal academic writing norms. "
            "No specific disclosure required, but always cite your prior work.",
        )

    def _build_flags(
        self, passages: list[RecycledPassage], pct: float
    ) -> list[str]:
        flags = []
        if pct > self.high_pct:
            flags.append(
                f"Recycling rate {pct:.1f}% exceeds the 30% COPE threshold")
        elif pct > self.medium_pct:
            flags.append(
                f"Recycling rate {pct:.1f}% is in the 15-30% disclosure zone")

        verbatim = [p for p in passages if p.overlap_type == "verbatim"]
        if verbatim:
            flags.append(
                f"{len(verbatim)} verbatim passage(s) detected "
                f"(char Jaccard >= {self.char_thresh})")
        para_rec = [p for p in passages if p.overlap_type == "paraphrase"]
        if para_rec:
            flags.append(
                f"{len(para_rec)} paraphrase recycling instance(s) detected "
                f"via semantic similarity (cosine >= {self.sem_thresh})")
        return flags

    def _empty_result(self, reason: str) -> SelfPlagiarismResult:
        return SelfPlagiarismResult(
            overall_overlap_pct=0.0,
            risk_level="LOW",
            recycled_passages=[],
            source_breakdown={},
            flags=[reason],
            cope_guidance="Cannot assess without prior works corpus.",
        )
