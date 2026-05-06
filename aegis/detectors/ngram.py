"""
N-gram shingling + MinHash LSH similarity detector.

Uses character 5-grams + word 3-grams with MinHash (128 permutations)
as a fast pre-filter before expensive semantic checks. This approach
is robust to minor paraphrasing, synonym substitution, and word reordering.

Fills gap: Open-source tools use simple Jaccard on word sets; AEGIS uses
MinHash LSH for sub-linear time candidate retrieval over large corpora,
combined with character-level shingles that are harder to evade by simple
synonym substitution.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from datasketch import MinHash, MinHashLSH


@dataclass
class NGramMatch:
    query_segment: str
    source_label: str
    source_segment: str
    jaccard_estimate: float
    match_type: str          # "word_ngram" | "char_ngram"
    char_offset_query: Optional[int] = None


class NGramDetector:
    """
    Fast near-duplicate detection using MinHash LSH.

    Two separate indices:
      - Word 3-gram index: catches verbatim copy and light paraphrase
      - Character 5-gram index: catches obfuscated copy (typos, char substitution)
    """

    def __init__(
        self,
        word_n: int = 3,
        char_n: int = 5,
        num_perm: int = 128,
        word_threshold: float = 0.25,
        char_threshold: float = 0.40,
    ):
        self.word_n = word_n
        self.char_n = char_n
        self.num_perm = num_perm
        self.word_threshold = word_threshold
        self.char_threshold = char_threshold
        self._word_lsh: Optional[MinHashLSH] = None
        self._char_lsh: Optional[MinHashLSH] = None
        self._word_index: dict[str, tuple[str, str]] = {}  # key -> (label, text)
        self._char_index: dict[str, tuple[str, str]] = {}

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------

    def build_index(self, corpus: list[tuple[str, str]]) -> None:
        """
        corpus: list of (label, text) pairs (e.g., prior papers, reference texts)
        """
        self._word_lsh = MinHashLSH(threshold=self.word_threshold,
                                    num_perm=self.num_perm)
        self._char_lsh = MinHashLSH(threshold=self.char_threshold,
                                    num_perm=self.num_perm)
        self._word_index = {}
        self._char_index = {}

        for i, (label, text) in enumerate(corpus):
            paragraphs = self._split_paragraphs(text)
            for j, para in enumerate(paragraphs):
                key = f"{label}__p{j}"
                w_mh = self._word_minhash(para)
                c_mh = self._char_minhash(para)
                try:
                    self._word_lsh.insert(key, w_mh)
                except ValueError:
                    pass
                try:
                    self._char_lsh.insert(key, c_mh)
                except ValueError:
                    pass
                self._word_index[key] = (label, para)
                self._char_index[key] = (label, para)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def find_matches(
        self, query_text: str, min_segment_words: int = 30
    ) -> list[NGramMatch]:
        """
        Find similar passages in the indexed corpus.
        Returns matches sorted by descending Jaccard similarity.
        """
        if not self._word_lsh:
            return []

        results: list[NGramMatch] = []
        paragraphs = self._split_paragraphs(query_text)

        for para in paragraphs:
            if len(para.split()) < min_segment_words:
                continue

            w_mh = self._word_minhash(para)
            c_mh = self._char_minhash(para)

            # Word 3-gram candidates
            word_candidates = self._word_lsh.query(w_mh)
            for key in word_candidates:
                label, src_para = self._word_index[key]
                j = self._jaccard(para, src_para, mode="word")
                results.append(NGramMatch(
                    query_segment=para[:400],
                    source_label=label,
                    source_segment=src_para[:400],
                    jaccard_estimate=round(j, 3),
                    match_type="word_ngram",
                ))

            # Character 5-gram candidates
            char_candidates = self._char_lsh.query(c_mh)
            for key in char_candidates:
                if key in word_candidates:
                    continue
                label, src_para = self._char_index[key]
                j = self._jaccard(para, src_para, mode="char")
                results.append(NGramMatch(
                    query_segment=para[:400],
                    source_label=label,
                    source_segment=src_para[:400],
                    jaccard_estimate=round(j, 3),
                    match_type="char_ngram",
                ))

        results.sort(key=lambda x: x.jaccard_estimate, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Direct comparison (no index needed)
    # ------------------------------------------------------------------

    def compare(self, text_a: str, text_b: str) -> dict:
        """
        Direct document-level comparison without an index.
        Returns word Jaccard, char Jaccard, and combined score.
        """
        word_j = self._jaccard(text_a, text_b, mode="word")
        char_j = self._jaccard(text_a, text_b, mode="char")
        combined = 0.6 * word_j + 0.4 * char_j
        return {
            "word_ngram_jaccard": round(word_j, 3),
            "char_ngram_jaccard": round(char_j, 3),
            "combined_score": round(combined, 3),
            "flagged": combined >= self.word_threshold,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _word_shingles(self, text: str) -> set[str]:
        tokens = re.findall(r"\b[a-z]{2,}\b", text.lower())
        return {" ".join(tokens[i:i + self.word_n])
                for i in range(len(tokens) - self.word_n + 1)}

    def _char_shingles(self, text: str) -> set[str]:
        t = re.sub(r"\s+", " ", text.lower())
        return {t[i:i + self.char_n] for i in range(len(t) - self.char_n + 1)}

    def _word_minhash(self, text: str) -> MinHash:
        m = MinHash(num_perm=self.num_perm)
        for s in self._word_shingles(text):
            m.update(s.encode("utf-8"))
        return m

    def _char_minhash(self, text: str) -> MinHash:
        m = MinHash(num_perm=self.num_perm)
        for s in self._char_shingles(text):
            m.update(s.encode("utf-8"))
        return m

    def _jaccard(self, a: str, b: str, mode: str = "word") -> float:
        if mode == "word":
            sa, sb = self._word_shingles(a), self._word_shingles(b)
        else:
            sa, sb = self._char_shingles(a), self._char_shingles(b)
        if not sa and not sb:
            return 0.0
        inter = len(sa & sb)
        union = len(sa | sb)
        return inter / union if union else 0.0

    def _split_paragraphs(self, text: str, min_words: int = 20) -> list[str]:
        paras = re.split(r"\n\n+", text)
        return [p.strip() for p in paras
                if len(p.strip().split()) >= min_words]
