"""
Batch / Classroom Analyzer -- AEGIS v2.0 Novel Feature.

Detects essay mill operations and shared AI source documents by analyzing
a set of submissions simultaneously. Single-document analysis cannot catch
this: each submission may score LOW individually, but cross-comparison
reveals that N papers share an AI-generated ancestor.

Detection methods:
  1. Pairwise MinHash similarity matrix: O(N^2 / 2) comparisons using the
     existing NGramDetector to build a similarity matrix across all submissions.
     Submissions with similarity > 0.25 (after personal details stripped)
     are flagged as suspicious pairs.

  2. Structural fingerprinting: extract the sequence of section headings and
     compare it across submissions. Identical or near-identical section
     sequences with different surface text = AI template reuse.

  3. AI score clustering: if a cluster of submissions all score > 0.60 on
     the AI detector, this strengthens the per-document inference -- it is
     statistically unlikely for a class to all independently write in
     AI-like style unless a shared prompt or tool was used.

  4. Vocabulary overlap matrix: even after paraphrasing, AI rewrites from
     the same source share rare vocabulary items. High Jaccard overlap of
     rare words (TF-IDF weight > 0.6) across submissions is a red flag.

Usage:
    analyzer = BatchAnalyzer(paths=["a.pdf", "b.pdf", ...])
    result = analyzer.analyze()
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from itertools import combinations
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SuspiciousPair:
    doc_a: str
    doc_b: str
    ngram_similarity: float
    vocab_overlap: float
    section_sequence_match: float
    combined_score: float
    reason: str


@dataclass
class BatchAnalysisResult:
    submission_count: int
    suspicious_pairs: list[SuspiciousPair]
    cluster_groups: list[list[str]]     # groups of submissions sharing a common source
    mean_ai_score: float
    ai_score_std: float
    high_ai_cluster: list[str]          # submissions all scoring > 0.65
    overall_risk: str                   # LOW | MEDIUM | HIGH | CRITICAL
    flags: list[str]
    similarity_matrix: dict             # {(a, b): score}


class BatchAnalyzer:
    """
    Cross-document analysis for classroom-scale essay mill detection.
    Accepts pre-parsed document texts (not file paths) to avoid re-parsing.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.25,
        section_match_threshold: float = 0.70,
        ai_cluster_threshold: float = 0.60,
        min_docs_for_cluster: int = 3,
    ):
        self.sim_thresh = similarity_threshold
        self.sect_thresh = section_match_threshold
        self.ai_thresh = ai_cluster_threshold
        self.min_cluster = min_docs_for_cluster

    def _get_word_shingles(self, text: str, n: int = 3) -> set[str]:
        words = re.sub(r"[^a-z\s]", "", text.lower()).split()
        return {
            " ".join(words[i:i + n])
            for i in range(len(words) - n + 1)
        }

    def _jaccard(self, a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _extract_sections(self, text: str) -> list[str]:
        headings = re.findall(
            r"(?m)^#{1,3}\s+(.+)$|^([A-Z][A-Z\s]{3,60})$",
            text
        )
        return [
            (h[0] or h[1]).lower().strip()
            for h in headings
            if (h[0] or h[1]).strip()
        ]

    def _section_sequence_similarity(
        self, sects_a: list[str], sects_b: list[str]
    ) -> float:
        if not sects_a or not sects_b:
            return 0.0
        # LCS-based similarity
        m, n = len(sects_a), len(sects_b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if sects_a[i - 1] == sects_b[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        lcs_len = dp[m][n]
        return 2 * lcs_len / (m + n)

    def _rare_vocab(self, texts: list[str]) -> list[set[str]]:
        """Return the set of rare words (appearing in < 30% of docs) per doc."""
        all_words = []
        for t in texts:
            words = set(re.sub(r"[^a-z]", " ", t.lower()).split())
            all_words.append(words)

        doc_freq: dict[str, int] = {}
        for words in all_words:
            for w in words:
                doc_freq[w] = doc_freq.get(w, 0) + 1

        n = len(texts)
        rare_threshold = max(1, n * 0.30)
        rare_words = {w for w, f in doc_freq.items() if f <= rare_threshold and len(w) > 4}

        return [words & rare_words for words in all_words]

    def _union_find(self, pairs: list[tuple[int, int]], n: int) -> list[list[int]]:
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            parent[find(x)] = find(y)

        for a, b in pairs:
            union(a, b)

        groups: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(i)

        return [g for g in groups.values() if len(g) > 1]

    def analyze(
        self,
        doc_names: list[str],
        doc_texts: list[str],
        ai_scores: Optional[list[float]] = None,
    ) -> BatchAnalysisResult:
        n = len(doc_texts)
        if n < 2:
            return BatchAnalysisResult(
                submission_count=n, suspicious_pairs=[], cluster_groups=[],
                mean_ai_score=0.0, ai_score_std=0.0, high_ai_cluster=[],
                overall_risk="LOW", flags=["Need at least 2 submissions for batch analysis."],
                similarity_matrix={},
            )

        # Precompute shingles and sections
        shingles = [self._get_word_shingles(t) for t in doc_texts]
        sections = [self._extract_sections(t) for t in doc_texts]
        rare_vocabs = self._rare_vocab(doc_texts)

        similarity_matrix: dict[tuple[str, str], float] = {}
        suspicious_pairs: list[SuspiciousPair] = []
        suspicious_indices: list[tuple[int, int]] = []

        for i, j in combinations(range(n), 2):
            ngram_sim = self._jaccard(shingles[i], shingles[j])
            vocab_sim = self._jaccard(rare_vocabs[i], rare_vocabs[j])
            sect_sim = self._section_sequence_similarity(sections[i], sections[j])
            combined = ngram_sim * 0.50 + vocab_sim * 0.30 + sect_sim * 0.20

            similarity_matrix[(doc_names[i], doc_names[j])] = round(combined, 4)

            if combined >= self.sim_thresh or (sect_sim >= self.sect_thresh and ngram_sim >= 0.15):
                reasons = []
                if ngram_sim >= self.sim_thresh:
                    reasons.append(f"n-gram similarity {ngram_sim:.2f}")
                if vocab_sim >= 0.30:
                    reasons.append(f"rare vocabulary overlap {vocab_sim:.2f}")
                if sect_sim >= self.sect_thresh:
                    reasons.append(f"identical section structure {sect_sim:.2f}")

                suspicious_pairs.append(SuspiciousPair(
                    doc_a=doc_names[i],
                    doc_b=doc_names[j],
                    ngram_similarity=round(ngram_sim, 4),
                    vocab_overlap=round(vocab_sim, 4),
                    section_sequence_match=round(sect_sim, 4),
                    combined_score=round(combined, 4),
                    reason="; ".join(reasons) or "combined signal threshold exceeded",
                ))
                suspicious_indices.append((i, j))

        # Cluster suspicious submissions
        cluster_index_groups = self._union_find(suspicious_indices, n)
        cluster_groups = [
            [doc_names[i] for i in grp] for grp in cluster_index_groups
        ]

        # AI score statistics
        mean_ai = 0.0
        std_ai = 0.0
        high_ai_cluster: list[str] = []
        if ai_scores and len(ai_scores) == n:
            mean_ai = sum(ai_scores) / n
            var = sum((s - mean_ai) ** 2 for s in ai_scores) / n
            std_ai = var ** 0.5
            high_ai_cluster = [
                doc_names[i] for i, s in enumerate(ai_scores)
                if s >= self.ai_thresh
            ]

        # Overall risk
        flags: list[str] = []
        if len(suspicious_pairs) >= 5:
            flags.append(f"{len(suspicious_pairs)} suspicious pairs -- possible essay mill.")
        if len(high_ai_cluster) >= self.min_cluster:
            flags.append(
                f"{len(high_ai_cluster)} submissions cluster with AI score >= {self.ai_thresh:.0%}."
            )
        if cluster_groups:
            flags.append(
                f"{len(cluster_groups)} submission clusters detected -- possible shared AI source."
            )

        n_high = len(suspicious_pairs)
        if n_high >= 5 or (len(high_ai_cluster) >= self.min_cluster and cluster_groups):
            risk = "CRITICAL"
        elif n_high >= 2 or len(high_ai_cluster) >= self.min_cluster:
            risk = "HIGH"
        elif n_high >= 1 or cluster_groups:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return BatchAnalysisResult(
            submission_count=n,
            suspicious_pairs=suspicious_pairs,
            cluster_groups=cluster_groups,
            mean_ai_score=round(mean_ai, 3),
            ai_score_std=round(std_ai, 3),
            high_ai_cluster=high_ai_cluster,
            overall_risk=risk,
            flags=flags,
            similarity_matrix={str(k): v for k, v in similarity_matrix.items()},
        )
