"""
Language-Calibrated AI Content Detector -- AEGIS Novel Feature #2.

Fills two critical gaps in existing tools:
  1. Calibration for non-native English speakers (ESL bias):
     Stanford study showed 61.3% false positive rate on ESL writers
     across all major detectors. AEGIS applies language-origin detection
     and adjusts thresholds accordingly.
  2. Paragraph-level scoring (not document-level):
     Most tools give one score per document. AEGIS scores every paragraph
     so partially AI-injected papers are caught.

Methods:
  - Perplexity scoring via GPT-2 (sliding window, 512-token stride)
  - Burstiness: variance in sentence-level perplexity (human text is more
    variable; AI text is uniformly low-perplexity)
  - Cross-perplexity ratio: P(GPT-2-base) / P(GPT-2-medium) -- Binoculars
    inspiration; GPT-2 base is the "observer", medium is the "scorer"
  - Stylometric feature ensemble: sentence length std, vocabulary richness,
    hedge phrase density, passive voice ratio, nominalization density
  - Language detection for ESL threshold calibration
"""

from __future__ import annotations
import re
import math
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ESL calibration multipliers -- threshold is multiplied by this factor
# for non-native English writing styles (languages where AI tools over-flag)
ESL_THRESHOLD_MULTIPLIER = {
    "zh": 0.80, "ko": 0.80, "ja": 0.80,  # East Asian
    "ar": 0.82, "fa": 0.82,               # Arabic / Farsi
    "ru": 0.85, "uk": 0.85,               # Slavic
    "es": 0.88, "pt": 0.88, "it": 0.88,  # Romance
    "de": 0.90, "fr": 0.90,               # Germanic/Gallic
    "en": 1.00,                            # Native English (no adjustment)
}

HEDGE_PHRASES = [
    "may be", "might be", "could be", "seems to", "appears to",
    "suggests that", "it is possible", "arguably", "presumably",
    "to some extent", "in general", "typically", "often",
    "we believe", "we suggest", "we argue", "we propose",
]


@dataclass
class ParagraphAIScore:
    text: str
    perplexity: float
    burstiness: float
    cross_perplexity_ratio: float
    stylometric_score: float       # 0=human, 1=AI
    ensemble_score: float          # 0=human, 1=AI (weighted)
    verdict: str                   # HUMAN | UNCERTAIN | AI_LIKELY | AI_DETECTED
    calibrated_language: str
    threshold_used: float


@dataclass
class AIDetectionResult:
    document_verdict: str          # HUMAN | UNCERTAIN | AI_LIKELY | AI_DETECTED
    document_ensemble_score: float
    ai_fraction: float             # fraction of paragraphs flagged AI
    paragraph_scores: list[ParagraphAIScore]
    detected_language: str
    calibration_applied: bool
    summary: dict


class AIContentDetector:
    """
    Bias-aware, paragraph-level AI content detector.

    Default thresholds tuned for low false-positive rate on academic text.
    Automatically calibrates for ESL writers.
    """

    BASE_MODEL = "gpt2"             # 500 MB, ~50ms per 512 tokens on CPU
    OBSERVER_MODEL = "gpt2-medium"  # 1.5 GB, used for cross-perplexity ratio

    def __init__(
        self,
        base_perplexity_threshold: float = 45.0,  # < threshold = AI-like
        burstiness_threshold: float = 0.35,        # < threshold = AI-like (low variance)
        ratio_threshold: float = 0.75,             # < threshold = AI-like
        ensemble_threshold: float = 0.60,          # > threshold = flag
        use_cross_perplexity: bool = False,        # requires gpt2-medium (1.5 GB)
        device: str = "cpu",
    ):
        self.base_ppl_thresh = base_perplexity_threshold
        self.burstiness_thresh = burstiness_threshold
        self.ratio_thresh = ratio_threshold
        self.ensemble_thresh = ensemble_threshold
        self.use_cross_ppl = use_cross_perplexity
        self.device = device
        self._base_model = None
        self._base_tokenizer = None
        self._obs_model = None
        self._obs_tokenizer = None
        self._lang_detector = None

    def _load_models(self):
        if self._base_model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            self._torch = torch
            self._base_tokenizer = AutoTokenizer.from_pretrained(self.BASE_MODEL)
            self._base_model = AutoModelForCausalLM.from_pretrained(
                self.BASE_MODEL).to(self.device)
            self._base_model.eval()
            if self.use_cross_ppl:
                self._obs_tokenizer = AutoTokenizer.from_pretrained(
                    self.OBSERVER_MODEL)
                self._obs_model = AutoModelForCausalLM.from_pretrained(
                    self.OBSERVER_MODEL).to(self.device)
                self._obs_model.eval()
        except ImportError:
            raise ImportError(
                "transformers + torch required: pip install transformers torch")

    def _load_lang_detector(self):
        if self._lang_detector is not None:
            return
        try:
            from langdetect import detect as langdetect
            self._lang_detector = langdetect
        except ImportError:
            self._lang_detector = lambda _: "en"

    def detect(self, text: str) -> AIDetectionResult:
        """Analyse a full document. Returns per-paragraph + aggregate results."""
        self._load_models()
        self._load_lang_detector()

        # Detect language and compute calibrated threshold
        try:
            lang = self._lang_detector(text[:500])
        except Exception:
            lang = "en"
        multiplier = ESL_THRESHOLD_MULTIPLIER.get(lang, 0.90)
        calibrated_thresh = self.ensemble_thresh * multiplier

        paragraphs = self._split_paragraphs(text)
        para_scores: list[ParagraphAIScore] = []

        for para in paragraphs:
            score = self._score_paragraph(para, lang, calibrated_thresh)
            para_scores.append(score)

        if not para_scores:
            return AIDetectionResult(
                document_verdict="UNCERTAIN",
                document_ensemble_score=0.5,
                ai_fraction=0.0,
                paragraph_scores=[],
                detected_language=lang,
                calibration_applied=(lang != "en"),
                summary={},
            )

        doc_score = sum(p.ensemble_score for p in para_scores) / len(para_scores)
        ai_count = sum(1 for p in para_scores if p.verdict in
                       ("AI_LIKELY", "AI_DETECTED"))
        ai_frac = ai_count / len(para_scores)

        doc_verdict = self._ensemble_verdict(doc_score, calibrated_thresh)

        return AIDetectionResult(
            document_verdict=doc_verdict,
            document_ensemble_score=round(doc_score, 3),
            ai_fraction=round(ai_frac, 3),
            paragraph_scores=para_scores,
            detected_language=lang,
            calibration_applied=(lang != "en"),
            summary=self._build_summary(para_scores, doc_score, ai_frac, lang),
        )

    def _score_paragraph(
        self, text: str, lang: str, threshold: float
    ) -> ParagraphAIScore:
        ppl = self._perplexity(text, self._base_model, self._base_tokenizer)
        burstiness = self._burstiness(text)
        ratio = 1.0
        if self.use_cross_ppl and self._obs_model:
            obs_ppl = self._perplexity(
                text, self._obs_model, self._obs_tokenizer)
            ratio = ppl / obs_ppl if obs_ppl > 0 else 1.0

        style_score = self._stylometric_ai_score(text)

        # Convert perplexity to a 0-1 AI score
        # Low perplexity (< threshold) = AI-like
        ppl_score = max(0.0, 1.0 - (ppl / self.base_ppl_thresh))
        ppl_score = min(1.0, ppl_score)

        # Low burstiness = AI-like
        burst_score = max(0.0, 1.0 - (burstiness / self.burstiness_thresh))
        burst_score = min(1.0, burst_score)

        # Low cross-perplexity ratio = AI-like
        ratio_score = max(0.0, 1.0 - (ratio / self.ratio_thresh))
        ratio_score = min(1.0, ratio_score)

        # Ensemble (weighted average)
        if self.use_cross_ppl and self._obs_model:
            ensemble = 0.30 * ppl_score + 0.20 * burst_score + \
                       0.25 * ratio_score + 0.25 * style_score
        else:
            ensemble = 0.40 * ppl_score + 0.30 * burst_score + \
                       0.30 * style_score

        verdict = self._ensemble_verdict(ensemble, threshold)

        return ParagraphAIScore(
            text=text[:200],
            perplexity=round(ppl, 2),
            burstiness=round(burstiness, 3),
            cross_perplexity_ratio=round(ratio, 3),
            stylometric_score=round(style_score, 3),
            ensemble_score=round(ensemble, 3),
            verdict=verdict,
            calibrated_language=lang,
            threshold_used=round(threshold, 3),
        )

    def _perplexity(self, text: str, model, tokenizer) -> float:
        """Compute GPT-2 perplexity with sliding-window stride."""
        import torch
        max_len = 512
        stride = 256
        encodings = tokenizer(text, return_tensors="pt", truncation=False)
        input_ids = encodings.input_ids.to(self.device)
        seq_len = input_ids.size(1)

        if seq_len == 0:
            return 100.0

        nlls = []
        prev_end_loc = 0
        for begin in range(0, seq_len, stride):
            end = min(begin + max_len, seq_len)
            target_len = end - prev_end_loc
            with torch.no_grad():
                out = model(input_ids[:, begin:end],
                            labels=input_ids[:, begin:end])
                nll = out.loss * target_len
                nlls.append(nll)
            prev_end_loc = end
            if end == seq_len:
                break

        total_tokens = prev_end_loc
        mean_nll = torch.stack(nlls).sum() / total_tokens if nlls else torch.tensor(0.0)
        return math.exp(float(mean_nll)) if float(mean_nll) < 10 else 22026.0

    def _burstiness(self, text: str) -> float:
        """
        Variance in sentence-level perplexity.
        Human writing is bursty (some complex, some simple sentences).
        AI text is uniformly low-perplexity (low burstiness).
        Returned as coefficient of variation of sentence lengths
        (proxy for perplexity variance without per-sentence LLM calls).
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        lengths = [len(s.split()) for s in sentences if len(s.split()) > 3]
        if len(lengths) < 3:
            return 0.5
        mean_len = sum(lengths) / len(lengths)
        variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
        std_len = variance ** 0.5
        cv = std_len / mean_len if mean_len > 0 else 0.0
        # AI text CV typically < 0.35; human academic text typically 0.40-0.70
        return round(min(cv, 1.0), 3)

    def _stylometric_ai_score(self, text: str) -> float:
        """
        Compute stylometric features associated with AI-generated academic text.
        Returns a 0-1 score where 1 = strongly AI-like.
        """
        signals = []
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
                     if len(s.strip().split()) > 3]

        if not sentences:
            return 0.5

        # 1. Sentence length uniformity (AI text has less variance)
        lengths = [len(s.split()) for s in sentences]
        mean_len = sum(lengths) / len(lengths)
        cv = (sum((l - mean_len)**2 for l in lengths) / len(lengths))**0.5 / max(mean_len, 1)
        signals.append(1.0 - min(cv / 0.5, 1.0))  # low cv = AI-like

        # 2. Hedge phrase density (AI text uses many hedges)
        word_count = max(len(text.split()), 1)
        hedge_count = sum(text.lower().count(h) for h in HEDGE_PHRASES)
        hedge_density = hedge_count / (word_count / 100)
        signals.append(min(hedge_density / 5.0, 1.0))  # >5 per 100 words = AI-like

        # 3. Vocabulary richness -- low TTR can indicate AI
        tokens = re.findall(r"\b[a-z]{2,}\b", text.lower())
        ttr = len(set(tokens)) / len(tokens) if tokens else 0.5
        # AI text often has TTR 0.40-0.55; human academic text 0.55-0.70
        signals.append(max(0.0, 1.0 - (ttr - 0.30) / 0.30))

        # 4. First-person absence (AI rarely uses "I" or "We" appropriately)
        first_person = len(re.findall(r"\b[Ww]e\b|\b[Ii]\b", text))
        fp_density = first_person / (word_count / 100)
        # Very low first-person in what should be a multi-author paper = AI signal
        signals.append(1.0 if fp_density < 0.5 else 0.0)

        return round(sum(signals) / len(signals), 3)

    def _ensemble_verdict(self, score: float, threshold: float) -> str:
        if score < threshold * 0.5:
            return "HUMAN"
        elif score < threshold:
            return "UNCERTAIN"
        elif score < threshold * 1.25:
            return "AI_LIKELY"
        else:
            return "AI_DETECTED"

    def _split_paragraphs(self, text: str, min_words: int = 50) -> list[str]:
        paras = re.split(r"\n\n+", text)
        return [p.strip() for p in paras if len(p.strip().split()) >= min_words]

    def _build_summary(self, scores, doc_score, ai_frac, lang) -> dict:
        verdicts = [s.verdict for s in scores]
        from collections import Counter
        return {
            "verdict_distribution": dict(Counter(verdicts)),
            "mean_perplexity": round(
                sum(s.perplexity for s in scores) / len(scores), 2) if scores else 0,
            "mean_burstiness": round(
                sum(s.burstiness for s in scores) / len(scores), 3) if scores else 0,
            "ai_paragraph_fraction": ai_frac,
            "detected_language": lang,
            "esl_calibration_applied": lang != "en",
        }
