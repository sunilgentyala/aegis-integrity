"""
Stylometric Authorship Profiler -- AEGIS Novel Feature #3.

Integrated into plagiarism pipeline (no existing open-source tool does this).
Fills two gaps:
  1. Intra-document style change detection: catching ghostwriting or
     multi-author sections in a single submission
  2. Author profile deviation: comparing current submission against an
     established writing profile (Burrows' Delta approach)

Features extracted per text segment:
  - Function word frequencies (50 most common English function words)
  - Average and std of sentence length (words)
  - Type-token ratio (TTR)
  - Hapax legomena ratio
  - Punctuation density (commas, semicolons, colons per sentence)
  - Passive voice ratio (heuristic: "is/are/was/were + past participle")
  - Nominalization density (words ending in -tion, -ness, -ment, -ity)
  - Readability scores (Flesch-Kincaid Grade Level)
  - Hedge phrase frequency
  - Paragraph length distribution
"""

from __future__ import annotations
import re
import math
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter


FUNCTION_WORDS = [
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "it",
    "for", "not", "on", "with", "he", "as", "you", "do", "at", "this",
    "but", "his", "by", "from", "they", "we", "say", "her", "she", "or",
    "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "when",
]

HEDGE_WORDS = [
    "possibly", "perhaps", "likely", "generally", "often", "sometimes",
    "usually", "typically", "approximately", "roughly", "nearly",
    "presumably", "apparently", "seemingly", "arguably", "potentially",
]

NOMINALIZATION_SUFFIXES = (
    "tion", "sion", "ness", "ment", "ity", "ism", "ance", "ence", "ery",
)

PASSIVE_PATTERN = re.compile(
    r"\b(is|are|was|were|be|been|being)\s+"
    r"(\w+ed|shown|demonstrated|proposed|observed|found|given|known|"
    r"used|applied|performed|conducted|analyzed|measured|evaluated)\b",
    re.IGNORECASE,
)


@dataclass
class StyleProfile:
    """Numeric stylometric fingerprint of a text segment."""
    label: str
    word_count: int
    avg_sentence_len: float
    std_sentence_len: float
    ttr: float
    hapax_ratio: float
    punct_density: float           # punctuation marks per sentence
    passive_ratio: float           # passive sentences / total sentences
    nominalization_density: float  # nominalizations per 100 words
    readability_fk_grade: float    # Flesch-Kincaid Grade Level
    hedge_density: float           # hedge words per 100 words
    function_word_vector: list[float]  # normalised freq for 50 function words
    yule_k: float

    def to_vector(self) -> list[float]:
        """Flat numeric vector for distance computation."""
        return [
            self.avg_sentence_len / 50.0,
            self.std_sentence_len / 30.0,
            self.ttr,
            self.hapax_ratio,
            self.punct_density / 5.0,
            self.passive_ratio,
            self.nominalization_density / 10.0,
            self.readability_fk_grade / 20.0,
            self.hedge_density / 5.0,
            self.yule_k / 100.0,
        ] + self.function_word_vector


@dataclass
class StyleChangePoint:
    segment_index: int
    text_preview: str
    delta_distance: float      # Burrows' Delta from document baseline
    flagged: bool
    reason: str


@dataclass
class StyleAnalysisResult:
    document_profile: StyleProfile
    segment_profiles: list[StyleProfile]
    change_points: list[StyleChangePoint]
    author_deviation: Optional[float]   # None if no baseline profile
    is_consistent: bool
    consistency_score: float            # 1.0 = perfectly consistent
    flags: list[str]


class StylometricAnalyzer:
    """
    Extract stylometric features and detect authorship inconsistencies.
    """

    def __init__(
        self,
        segment_size_words: int = 300,
        change_threshold: float = 0.40,  # Burrows' Delta threshold for flagging
        author_deviation_threshold: float = 0.50,
    ):
        self.segment_size = segment_size_words
        self.change_threshold = change_threshold
        self.deviation_threshold = author_deviation_threshold

    def profile_text(self, text: str, label: str = "document") -> StyleProfile:
        """Extract a full stylometric profile from text."""
        text = self._clean(text)
        tokens = re.findall(r"\b[a-z]{2,}\b", text.lower())
        sentences = self._split_sentences(text)

        word_count = len(tokens)
        if word_count < 20:
            return self._empty_profile(label)

        # Sentence length stats
        sent_lens = [len(re.findall(r"\b\w+\b", s)) for s in sentences
                     if len(s.split()) > 2]
        avg_len = sum(sent_lens) / len(sent_lens) if sent_lens else 0.0
        std_len = math.sqrt(
            sum((l - avg_len)**2 for l in sent_lens) / len(sent_lens)
        ) if len(sent_lens) > 1 else 0.0

        # TTR and hapax
        freq = Counter(tokens)
        v = len(freq)
        hapax = sum(1 for c in freq.values() if c == 1)
        ttr = v / word_count if word_count else 0.0
        hapax_ratio = hapax / v if v else 0.0

        # Yule's K
        n = word_count
        m2 = sum(c * (c - 1) for c in freq.values())
        yule_k = 1e4 * m2 / (n * (n - 1)) if n > 1 else 0.0

        # Punctuation density
        punct_counts = [len(re.findall(r"[,;:]", s)) for s in sentences
                        if len(s.split()) > 2]
        punct_density = (sum(punct_counts) / len(punct_counts)
                         if punct_counts else 0.0)

        # Passive voice ratio
        passive_sents = sum(1 for s in sentences
                            if PASSIVE_PATTERN.search(s))
        passive_ratio = passive_sents / len(sentences) if sentences else 0.0

        # Nominalization density
        noms = sum(1 for t in tokens
                   if any(t.endswith(suf) for suf in NOMINALIZATION_SUFFIXES))
        nom_density = noms / (word_count / 100) if word_count else 0.0

        # Readability (Flesch-Kincaid Grade Level approximation)
        syllables = sum(self._count_syllables(t) for t in tokens)
        fk_grade = (0.39 * avg_len + 11.8 * (syllables / word_count) - 15.59
                    if word_count and sentences else 0.0)

        # Hedge density
        hedge_count = sum(text.lower().count(h) for h in HEDGE_WORDS)
        hedge_density = hedge_count / (word_count / 100) if word_count else 0.0

        # Function word vector (normalised frequency)
        fw_vector = []
        for fw in FUNCTION_WORDS:
            fw_vector.append(freq.get(fw, 0) / word_count)

        return StyleProfile(
            label=label,
            word_count=word_count,
            avg_sentence_len=round(avg_len, 2),
            std_sentence_len=round(std_len, 2),
            ttr=round(ttr, 4),
            hapax_ratio=round(hapax_ratio, 4),
            punct_density=round(punct_density, 3),
            passive_ratio=round(passive_ratio, 3),
            nominalization_density=round(nom_density, 2),
            readability_fk_grade=round(fk_grade, 2),
            hedge_density=round(hedge_density, 2),
            function_word_vector=[round(v, 5) for v in fw_vector],
            yule_k=round(yule_k, 2),
        )

    def analyze(
        self,
        text: str,
        author_baseline: Optional[StyleProfile] = None,
    ) -> StyleAnalysisResult:
        """
        Full stylometric analysis: style change detection + author deviation.
        """
        doc_profile = self.profile_text(text, label="full_document")
        segments = self._segment_text(text, self.segment_size)
        seg_profiles = [
            self.profile_text(seg, label=f"segment_{i}")
            for i, seg in enumerate(segments)
        ]

        # Change point detection using Burrows' Delta between segments
        change_points = []
        for i, sp in enumerate(seg_profiles):
            delta = self._burrows_delta(doc_profile, sp)
            flagged = delta > self.change_threshold
            change_points.append(StyleChangePoint(
                segment_index=i,
                text_preview=segments[i][:120] + "...",
                delta_distance=round(delta, 3),
                flagged=flagged,
                reason=(
                    f"Style deviation {delta:.2f} exceeds threshold "
                    f"{self.change_threshold:.2f}"
                    if flagged else "Within normal style range"
                ),
            ))

        # Author deviation from baseline
        author_deviation = None
        if author_baseline:
            author_deviation = round(
                self._burrows_delta(author_baseline, doc_profile), 3)

        flagged_segments = [cp for cp in change_points if cp.flagged]
        consistency_score = round(
            1.0 - len(flagged_segments) / max(len(change_points), 1), 3)
        is_consistent = consistency_score >= 0.80

        flags = []
        if flagged_segments:
            flags.append(
                f"{len(flagged_segments)} segment(s) show significant style "
                f"change (possible ghostwriting or multi-author sections)")
        if author_deviation and author_deviation > self.deviation_threshold:
            flags.append(
                f"Document style deviates from author baseline "
                f"(delta={author_deviation:.2f})")

        return StyleAnalysisResult(
            document_profile=doc_profile,
            segment_profiles=seg_profiles,
            change_points=change_points,
            author_deviation=author_deviation,
            is_consistent=is_consistent,
            consistency_score=consistency_score,
            flags=flags,
        )

    def _burrows_delta(self, profile_a: StyleProfile,
                       profile_b: StyleProfile) -> float:
        """
        Simplified Burrows' Delta: mean absolute z-score difference
        over the function word frequency vector + scalar features.
        """
        vec_a = profile_a.to_vector()
        vec_b = profile_b.to_vector()
        if len(vec_a) != len(vec_b) or not vec_a:
            return 0.0
        # Compute z-score-like difference (no corpus std available;
        # use absolute difference normalized by expected range)
        diffs = [abs(a - b) for a, b in zip(vec_a, vec_b)]
        return sum(diffs) / len(diffs)

    def _segment_text(self, text: str, size: int) -> list[str]:
        words = text.split()
        return [" ".join(words[i:i + size])
                for i in range(0, len(words), size)
                if len(words[i:i + size]) >= size // 2]

    def _split_sentences(self, text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [p.strip() for p in parts if len(p.strip().split()) > 2]

    def _count_syllables(self, word: str) -> int:
        word = word.lower()
        vowels = "aeiouy"
        count = 0
        prev_vowel = False
        for ch in word:
            is_vowel = ch in vowels
            if is_vowel and not prev_vowel:
                count += 1
            prev_vowel = is_vowel
        if word.endswith("e"):
            count = max(1, count - 1)
        return max(1, count)

    def _clean(self, text: str) -> str:
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\[\d+\]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _empty_profile(self, label: str) -> StyleProfile:
        return StyleProfile(
            label=label, word_count=0, avg_sentence_len=0.0,
            std_sentence_len=0.0, ttr=0.0, hapax_ratio=0.0,
            punct_density=0.0, passive_ratio=0.0, nominalization_density=0.0,
            readability_fk_grade=0.0, hedge_density=0.0,
            function_word_vector=[0.0] * len(FUNCTION_WORDS), yule_k=0.0,
        )
