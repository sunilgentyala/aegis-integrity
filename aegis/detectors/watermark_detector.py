"""
LLM Watermark Analysis -- AEGIS v2.0 experimental feature.

Two distinct capabilities live here, and they must not be confused:

1. EXPERIMENTAL token-distribution anomaly analysis (default mode).
   A keyless heuristic that simulates a green/red vocabulary split using a
   seed derived only from a hash of the previous word. It has NO relationship
   to any real LLM provider's watermark key, seeding scheme, or tokenizer --
   the "green list" it tests against is fabricated locally, not recovered
   from any actual deployment. It can surface a statistical anomaly in token
   distribution, but it CANNOT confirm that a document was produced by a
   watermarked model, and it CANNOT be attributed to any specific provider
   (GPT-4, Gemini, Claude, or otherwise). Results from this mode never affect
   the overall integrity risk score -- see WatermarkResult.affects_overall_risk.

2. VERIFIED_SCHEME known-scheme watermark verification (opt-in).
   Intended for the case where the actual watermark scheme, tokenizer, and
   key/seeding-scheme are known and supplied by the caller. AEGIS does not
   currently ship a real implementation of any provider's scheme, so this
   mode always reports UNSUPPORTED_CONFIGURATION rather than silently
   falling back to the heuristic above.

The statistical design of the heuristic is loosely modeled on the published
green-list watermarking literature (cited below) purely so the z-test has a
principled shape. That is not evidence that the heuristic can detect those
schemes without the real key -- it cannot.

References:
  Kirchenbauer et al. (2023). A Watermark for Large Language Models. ICML.
  Zhao et al. (2023). Provable Robust Watermarking for AI-Generated Text. ICLR.
  Hu et al. (2023). Unbiased Watermark for Large Language Models. ArXiv.
"""

from __future__ import annotations
import math
import hashlib
import logging
from dataclasses import dataclass, field
from collections import Counter
from enum import Enum
from typing import Literal, Optional

logger = logging.getLogger(__name__)


class WatermarkMode(str, Enum):
    DISABLED = "disabled"
    EXPERIMENTAL = "experimental"
    VERIFIED_SCHEME = "verified_scheme"


class DetectorExecutionStatus(str, Enum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


EvidenceStatus = Literal[
    "not_evaluated",
    "experimental",
    "unverified",
    "scheme_verified",
    "failed",
]

_EXPERIMENTAL_LIMITATIONS = [
    "This is a keyless heuristic. It does not know the real watermark key, "
    "seeding scheme, or tokenizer used by any LLM provider.",
    "A flagged anomaly is not proof that the document is AI-generated or "
    "watermarked -- repetitive technical vocabulary (common in academic "
    "writing) can also elevate the score.",
    "The z > 4.0 / z > 2.5 thresholds are theoretical bounds under the "
    "heuristic's own fabricated null distribution, not an empirically "
    "measured false-positive rate on real documents.",
    "This result does not affect the overall integrity risk score.",
]


@dataclass
class WatermarkResult:
    status: DetectorExecutionStatus
    mode: WatermarkMode
    verdict: str
    score: float = 0.0
    confidence: float = 0.0
    p_value: Optional[float] = None
    z_score: Optional[float] = None
    tokens_evaluated: int = 0
    minimum_tokens_required: int = 200
    watermark_scheme: Optional[str] = None
    tokenizer_name: Optional[str] = None
    configuration_validated: bool = False
    evidence_status: EvidenceStatus = "not_evaluated"
    affects_overall_risk: bool = False
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    error_code: Optional[str] = None
    detector_version: str = "2.1.0"

    # Populated only when the experimental heuristic actually ran.
    green_token_fraction: Optional[float] = None
    expected_green_fraction: Optional[float] = None
    entropy_score: Optional[float] = None
    rank_skew: Optional[float] = None
    details: dict = field(default_factory=dict)


class LLMWatermarkDetector:
    """
    Keyless token-distribution anomaly heuristic (EXPERIMENTAL mode), with an
    opt-in, currently-unimplemented hook for known-scheme verification
    (VERIFIED_SCHEME mode).

    Do not treat an EXPERIMENTAL verdict as confirmation of a watermark --
    see the module docstring for why. `affects_overall_risk` on the returned
    WatermarkResult is the source of truth for whether a caller may fold this
    result into a risk score; it is always False except for a successfully
    validated VERIFIED_SCHEME run (not currently implemented).
    """

    def __init__(
        self,
        mode: WatermarkMode = WatermarkMode.EXPERIMENTAL,
        gamma: float = 0.50,          # expected fraction of green tokens (0.5 = balanced split)
        z_threshold: float = 4.0,     # z-score above which the heuristic flags an anomaly strongly
        z_suspicious: float = 2.5,    # z-score above which the heuristic flags a mild anomaly
        min_tokens: int = 200,        # minimum tokens before the heuristic will report a verdict
        vocab_size: int = 50257,      # GPT-2 vocabulary size; used only to size the fabricated split
        watermark_scheme: Optional[str] = None,
        tokenizer_name: Optional[str] = None,
    ):
        self.mode = mode
        self.gamma = gamma
        self.z_threshold = z_threshold
        self.z_suspicious = z_suspicious
        self.min_tokens = min_tokens
        self.vocab_size = vocab_size
        self.watermark_scheme = watermark_scheme
        self.tokenizer_name = tokenizer_name

    # ------------------------------------------------------------------
    # Experimental heuristic internals
    # ------------------------------------------------------------------

    def _tokenize_simple(self, text: str) -> list[int]:
        """
        Word-level approximation of token IDs via a deterministic hash.
        This is NOT the tokenizer used by any real LLM -- it exists only so
        the heuristic below has integers to bucket into a fabricated
        green/red split.
        """
        words = text.lower().split()
        return [
            int(hashlib.md5(w.encode()).hexdigest(), 16) % self.vocab_size
            for w in words
            if w.isalpha()
        ]

    def _simulate_green_list(self, prev_token: int, vocab_size: int) -> set[int]:
        """
        Fabricate a green list seeded only on a hash of prev_token. This is
        NOT a real watermark scheme's seeding function and does not use any
        secret key -- it is a locally-generated null against which the
        observed token sequence is compared for excess concentration.
        """
        rng_seed = hashlib.sha256(str(prev_token).encode()).digest()
        seed_int = int.from_bytes(rng_seed[:4], "big")
        import random
        rng = random.Random(seed_int)
        all_tokens = list(range(vocab_size))
        rng.shuffle(all_tokens)
        split = int(vocab_size * self.gamma)
        return set(all_tokens[:split])

    def _kirchenbauer_z_score(self, tokens: list[int]) -> tuple[float, float, float]:
        """
        Returns (z_score, p_value, green_fraction) for the token sequence
        against the fabricated null above. One-sided test: H0: p = gamma,
        H1: p > gamma.
        """
        green_count = 0
        total = 0
        for i in range(1, len(tokens)):
            green_list = self._simulate_green_list(tokens[i - 1], self.vocab_size)
            if tokens[i] in green_list:
                green_count += 1
            total += 1

        if total == 0:
            return 0.0, 0.5, self.gamma

        green_frac = green_count / total
        std = math.sqrt(self.gamma * (1 - self.gamma) / total)
        z = (green_frac - self.gamma) / std if std > 0 else 0.0
        p = _norm_sf(z)
        return z, p, green_frac

    def _entropy_analysis(self, tokens: list[int]) -> float:
        """
        Unigram entropy of the token sequence, normalized to 0-1 by
        log(distinct token count). Lower = more concentrated distribution.
        """
        counts = Counter(tokens)
        total = len(tokens)
        if total == 0:
            return 0.0
        entropy = 0.0
        for c in counts.values():
            p = c / total
            entropy -= p * math.log(p)
        max_entropy = math.log(min(len(counts), self.vocab_size))
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _rank_skew(self, tokens: list[int]) -> float:
        """Fraction of total token mass held by the top decile of distinct tokens."""
        counts = Counter(tokens)
        sorted_counts = sorted(counts.values(), reverse=True)
        total = sum(sorted_counts)
        if total == 0 or len(sorted_counts) < 2:
            return 0.0
        top_10_pct = max(1, len(sorted_counts) // 10)
        return sum(sorted_counts[:top_10_pct]) / total

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, text: str) -> WatermarkResult:
        if self.mode == WatermarkMode.DISABLED:
            return WatermarkResult(
                status=DetectorExecutionStatus.SKIPPED,
                mode=self.mode,
                verdict="SKIPPED",
                evidence_status="not_evaluated",
                affects_overall_risk=False,
                watermark_scheme=self.watermark_scheme,
                tokenizer_name=self.tokenizer_name,
            )

        if self.mode == WatermarkMode.VERIFIED_SCHEME:
            return self._verified_scheme_unsupported()

        return self._run_experimental(text)

    def _verified_scheme_unsupported(self) -> WatermarkResult:
        return WatermarkResult(
            status=DetectorExecutionStatus.UNAVAILABLE,
            mode=self.mode,
            verdict="UNSUPPORTED_CONFIGURATION",
            evidence_status="failed",
            affects_overall_risk=False,
            configuration_validated=False,
            watermark_scheme=self.watermark_scheme,
            tokenizer_name=self.tokenizer_name,
            error_code="NO_VERIFIED_SCHEME_IMPLEMENTED",
            warnings=[
                "VERIFIED_SCHEME mode was requested, but AEGIS does not "
                "currently implement a known-scheme watermark verifier for "
                f"scheme={self.watermark_scheme!r}. No known-scheme signal "
                "was produced; this configuration does not silently fall "
                "back to the experimental heuristic."
            ],
            limitations=[_EXPERIMENTAL_LIMITATIONS[-1]],
        )

    def _run_experimental(self, text: str) -> WatermarkResult:
        tokens = self._tokenize_simple(text)

        if len(tokens) < self.min_tokens:
            return WatermarkResult(
                status=DetectorExecutionStatus.COMPLETED,
                mode=self.mode,
                verdict="INSUFFICIENT_TEXT",
                tokens_evaluated=len(tokens),
                minimum_tokens_required=self.min_tokens,
                evidence_status="experimental",
                affects_overall_risk=False,
                tokenizer_name="hash-approximation (not a real LLM tokenizer)",
                warnings=[
                    f"{len(tokens)} tokens were evaluated; at least "
                    f"{self.min_tokens} are required for a reliable read."
                ],
                limitations=list(_EXPERIMENTAL_LIMITATIONS),
                details={"reason": f"Only {len(tokens)} tokens; need {self.min_tokens}"},
            )

        try:
            z, p, green_frac = self._kirchenbauer_z_score(tokens)
            entropy = self._entropy_analysis(tokens)
            skew = self._rank_skew(tokens)
        except Exception as exc:
            logger.warning("Watermark heuristic analysis failed: %s", exc)
            return WatermarkResult(
                status=DetectorExecutionStatus.FAILED,
                mode=self.mode,
                verdict="ANALYSIS_FAILED",
                tokens_evaluated=len(tokens),
                minimum_tokens_required=self.min_tokens,
                evidence_status="failed",
                affects_overall_risk=False,
                error_code="ANALYSIS_EXCEPTION",
                warnings=[f"Analysis raised an exception: {exc}"],
                limitations=list(_EXPERIMENTAL_LIMITATIONS),
            )

        anomalous = z >= self.z_suspicious or (entropy < 0.45 and skew > 0.72)
        if anomalous:
            verdict = "STATISTICAL_ANOMALY"
            confidence = 0.4 + min(0.55, max(0.0, z - self.z_suspicious) * 0.15)
        else:
            verdict = "NO_STATISTICAL_ANOMALY"
            confidence = max(0.0, 1.0 - abs(z) / self.z_threshold) if self.z_threshold else 0.0

        return WatermarkResult(
            status=DetectorExecutionStatus.COMPLETED,
            mode=self.mode,
            verdict=verdict,
            score=round(min(1.0, max(0.0, z / self.z_threshold)), 3) if self.z_threshold else 0.0,
            confidence=round(min(confidence, 0.99), 3),
            p_value=round(p, 8),
            z_score=round(z, 4),
            tokens_evaluated=len(tokens),
            minimum_tokens_required=self.min_tokens,
            watermark_scheme=None,
            tokenizer_name="hash-approximation (not a real LLM tokenizer)",
            configuration_validated=False,
            evidence_status="experimental",
            affects_overall_risk=False,
            warnings=(
                ["The experimental heuristic flagged a token-distribution anomaly."]
                if anomalous else []
            ),
            limitations=list(_EXPERIMENTAL_LIMITATIONS),
            green_token_fraction=round(green_frac, 4),
            expected_green_fraction=self.gamma,
            entropy_score=round(entropy, 4),
            rank_skew=round(skew, 4),
            details={
                "z_threshold": self.z_threshold,
                "z_suspicious_threshold": self.z_suspicious,
                "p_value_type": "one-sided (H1: green fraction > gamma), theoretical",
                "interpretation": (
                    "Elevated green-list-style token concentration relative to the "
                    "heuristic's fabricated null. This is NOT evidence of a specific "
                    "watermark scheme or provider." if anomalous else
                    "No statistically significant anomaly detected by this heuristic."
                ),
            },
        )


def _norm_sf(z: float) -> float:
    """Survival function (1 - CDF) of the standard normal, Abramowitz & Stegun approximation."""
    if z < -10:
        return 1.0
    if z > 10:
        return 1e-20
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    poly = t * (0.319381530 + t * (
        -0.356563782 + t * (
            1.781477937 + t * (
                -1.821255978 + t * 1.330274429))))
    phi = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    p = phi * poly
    return p if z >= 0 else 1.0 - p
