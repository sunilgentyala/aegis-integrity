"""
Text normalization and sentence segmentation for academic documents.
"""

from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass


@dataclass
class Sentence:
    text: str
    start: int
    end: int
    section: str


@dataclass
class Paragraph:
    text: str
    sentences: list[Sentence]
    section: str
    index: int


class Preprocessor:
    """
    Clean and segment academic text into paragraphs and sentences.
    Uses spaCy when available; falls back to regex sentence splitting.
    """

    def __init__(self, use_spacy: bool = True):
        self._nlp = None
        if use_spacy:
            try:
                import spacy
                self._nlp = spacy.load("en_core_web_sm",
                                       disable=["ner", "lemmatizer"])
            except (ImportError, OSError):
                pass  # graceful fallback

    def clean(self, text: str) -> str:
        """Normalize Unicode, remove control chars, collapse whitespace."""
        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def paragraphs(self, text: str, section: str = "body") -> list[Paragraph]:
        """Split cleaned text into Paragraph objects."""
        text = self.clean(text)
        raw_paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        result = []
        for i, para_text in enumerate(raw_paras):
            sents = self.sentences(para_text, section=section)
            result.append(Paragraph(
                text=para_text, sentences=sents,
                section=section, index=i,
            ))
        return result

    def sentences(self, text: str, section: str = "body") -> list[Sentence]:
        """Segment text into sentences."""
        text = self.clean(text)
        if self._nlp:
            return self._spacy_sentences(text, section)
        return self._regex_sentences(text, section)

    def _spacy_sentences(self, text: str, section: str) -> list[Sentence]:
        doc = self._nlp(text)
        result = []
        for sent in doc.sents:
            s = sent.text.strip()
            if len(s) > 10:
                result.append(Sentence(
                    text=s,
                    start=sent.start_char,
                    end=sent.end_char,
                    section=section,
                ))
        return result

    def _regex_sentences(self, text: str, section: str) -> list[Sentence]:
        # Protect common abbreviations from splitting
        protected = re.sub(
            r"\b(e\.g|i\.e|et al|Fig|Tab|Eq|cf|vs|Dr|Mr|Mrs|Prof|al|approx)\.",
            lambda m: m.group(0).replace(".", "<DOT>"), text)
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", protected)
        result = []
        pos = 0
        for part in parts:
            restored = part.replace("<DOT>", ".")
            s = restored.strip()
            if len(s) > 10:
                start = text.find(s[:20], pos)
                end = start + len(s)
                result.append(Sentence(text=s, start=max(start, 0),
                                       end=end, section=section))
                pos = max(end, pos)
        return result

    def n_grams(self, text: str, n: int = 3, mode: str = "word") -> list[str]:
        """Extract word or character n-grams."""
        text = self.clean(text).lower()
        if mode == "char":
            tokens = list(text.replace(" ", "_"))
        else:
            tokens = re.findall(r"\b[a-z]{2,}\b", text)
        return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]

    def function_words(self, text: str) -> dict[str, int]:
        """Count occurrences of the 50 most common English function words."""
        fw = {
            "the", "be", "to", "of", "and", "a", "in", "that", "have", "it",
            "for", "not", "on", "with", "he", "as", "you", "do", "at", "this",
            "but", "his", "by", "from", "they", "we", "say", "her", "she", "or",
            "an", "will", "my", "one", "all", "would", "there", "their", "what",
            "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
            "when",
        }
        tokens = re.findall(r"\b[a-z]{1,10}\b", text.lower())
        return {w: tokens.count(w) for w in fw}

    def vocabulary_richness(self, text: str) -> dict[str, float]:
        """Type-token ratio, hapax legomena ratio, Yule's K."""
        tokens = re.findall(r"\b[a-z]{2,}\b", text.lower())
        if not tokens:
            return {"ttr": 0.0, "hapax_ratio": 0.0, "yule_k": 0.0}
        from collections import Counter
        freq = Counter(tokens)
        n = len(tokens)
        v = len(freq)
        hapax = sum(1 for c in freq.values() if c == 1)
        # Yule's K characteristic (measure of vocabulary richness)
        m2 = sum(c * (c - 1) for c in freq.values())
        yule_k = 1e4 * m2 / (n * (n - 1)) if n > 1 else 0.0
        return {
            "ttr": v / n,
            "hapax_ratio": hapax / v if v else 0.0,
            "yule_k": round(yule_k, 2),
        }
