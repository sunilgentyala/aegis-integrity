"""
AEGIS Analysis Pipeline -- orchestrates all detectors into a single result.

Execution order:
  1. Document parsing (multi-format)
  2. N-gram LSH similarity (fast pre-filter; word 3-gram + char 5-gram)
  3. Semantic similarity (SBERT dense retrieval; catches paraphrase)
  4. AI content detection (GPT-2 perplexity + stylometric ensemble)
  5. Citation integrity (Crossref DOI resolution; hallucination detection)
  6. Stylometric authorship profiling (Burrows' Delta; ghostwriting detection)
  7. Self-plagiarism detection (SBERT + n-gram against prior works)

Each detector runs independently; results are merged into AnalysisReport.
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from aegis.core.document import DocumentParser, ParsedDocument
from aegis.detectors.ngram import NGramDetector, NGramMatch
from aegis.detectors.semantic import SemanticDetector, SemanticMatch
from aegis.detectors.ai_detector import AIContentDetector, AIDetectionResult
from aegis.detectors.citation import CitationIntegrityDetector, CitationVerdict
from aegis.detectors.stylometric import StylometricAnalyzer, StyleAnalysisResult
from aegis.detectors.self_plagiarism import (
    SelfPlagiarismDetector, SelfPlagiarismResult)

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    # N-gram detector
    ngram_word_threshold: float = 0.25
    ngram_char_threshold: float = 0.40
    ngram_num_perm: int = 128

    # Semantic detector
    semantic_cosine_threshold: float = 0.82
    use_reranker: bool = True

    # AI detector
    ai_perplexity_threshold: float = 45.0
    ai_burstiness_threshold: float = 0.35
    ai_ensemble_threshold: float = 0.60
    use_cross_perplexity: bool = False

    # Citation detector
    citation_email: str = "aegis-check@example.com"
    citation_min_title_sim: float = 0.65
    citation_offline: bool = False

    # Stylometric
    stylometric_segment_size: int = 300
    stylometric_change_threshold: float = 0.40

    # Self-plagiarism
    self_plagiarism_char_threshold: float = 0.35
    self_plagiarism_semantic_threshold: float = 0.88
    self_plagiarism_medium_pct: float = 15.0
    self_plagiarism_high_pct: float = 30.0
    use_sbert_self_plagiarism: bool = True

    # Runtime
    device: str = "cpu"
    run_ai_detector: bool = True
    run_citation_check: bool = True
    run_semantic: bool = True
    run_stylometric: bool = True
    run_self_plagiarism: bool = True


@dataclass
class AnalysisReport:
    submission_path: str
    parsed_document: ParsedDocument

    # Detector results (None if detector was skipped)
    ngram_matches: list[NGramMatch] = field(default_factory=list)
    semantic_matches: list[SemanticMatch] = field(default_factory=list)
    ai_result: Optional[AIDetectionResult] = None
    citation_verdicts: list[CitationVerdict] = field(default_factory=list)
    stylometric_result: Optional[StyleAnalysisResult] = None
    self_plagiarism_result: Optional[SelfPlagiarismResult] = None

    # Aggregate risk scores (0.0 - 1.0)
    plagiarism_score: float = 0.0    # combined n-gram + semantic
    ai_score: float = 0.0            # from AI detector ensemble
    citation_score: float = 0.0     # fraction of flagged citations
    style_score: float = 0.0        # style inconsistency score
    self_recycle_score: float = 0.0 # recycling overlap percentage / 100

    # Final verdict
    overall_risk: str = "UNKNOWN"   # LOW | MEDIUM | HIGH | CRITICAL
    flags: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class AEGISPipeline:
    """
    Main entry point for AEGIS academic integrity analysis.

    Usage::

        pipeline = AEGISPipeline(config=PipelineConfig())
        pipeline.load_corpus([("paper_A", text_a), ("paper_B", text_b)])
        pipeline.load_prior_works([("my_conf_2023", prior_text)])
        report = pipeline.analyze("submission.pdf")
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.cfg = config or PipelineConfig()
        self._parser = DocumentParser()

        self._ngram = NGramDetector(
            word_threshold=self.cfg.ngram_word_threshold,
            char_threshold=self.cfg.ngram_char_threshold,
            num_perm=self.cfg.ngram_num_perm,
        )
        self._semantic = SemanticDetector(
            cosine_threshold=self.cfg.semantic_cosine_threshold,
            use_reranker=self.cfg.use_reranker,
            device=self.cfg.device,
        ) if self.cfg.run_semantic else None

        self._ai = AIContentDetector(
            base_perplexity_threshold=self.cfg.ai_perplexity_threshold,
            burstiness_threshold=self.cfg.ai_burstiness_threshold,
            ensemble_threshold=self.cfg.ai_ensemble_threshold,
            use_cross_perplexity=self.cfg.use_cross_perplexity,
            device=self.cfg.device,
        ) if self.cfg.run_ai_detector else None

        self._citation = CitationIntegrityDetector(
            email=self.cfg.citation_email,
            min_title_similarity=self.cfg.citation_min_title_sim,
            offline=self.cfg.citation_offline,
        ) if self.cfg.run_citation_check else None

        self._stylo = StylometricAnalyzer(
            segment_size_words=self.cfg.stylometric_segment_size,
            change_threshold=self.cfg.stylometric_change_threshold,
        ) if self.cfg.run_stylometric else None

        self._self_plag = SelfPlagiarismDetector(
            char_threshold=self.cfg.self_plagiarism_char_threshold,
            semantic_threshold=self.cfg.self_plagiarism_semantic_threshold,
            medium_risk_pct=self.cfg.self_plagiarism_medium_pct,
            high_risk_pct=self.cfg.self_plagiarism_high_pct,
            use_sbert=self.cfg.use_sbert_self_plagiarism,
            device=self.cfg.device,
        ) if self.cfg.run_self_plagiarism else None

        self._corpus_loaded = False

    # ------------------------------------------------------------------
    # Index loading
    # ------------------------------------------------------------------

    def load_corpus(self, corpus: list[tuple[str, str]]) -> None:
        """
        Load reference corpus (prior papers, known sources) for similarity search.
        corpus: list of (label, full_text) pairs.
        """
        self._ngram.build_index(corpus)
        if self._semantic:
            self._semantic.build_index(corpus)
        self._corpus_loaded = True
        logger.info("Corpus indexed: %d documents", len(corpus))

    def load_prior_works(self, prior_works: list[tuple[str, str]]) -> None:
        """
        Load author's own prior publications for self-plagiarism detection.
        prior_works: list of (label, full_text) pairs.
        """
        if self._self_plag:
            self._self_plag.load_prior_works(prior_works)
            logger.info("Prior works loaded: %d documents", len(prior_works))

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        submission_path: str,
        author_style_baseline=None,  # Optional[StyleProfile]
    ) -> AnalysisReport:
        """
        Run full AEGIS analysis on a submission file.

        submission_path: absolute path to PDF, DOCX, TEX, or TXT file.
        author_style_baseline: pre-computed StyleProfile from prior publications.
        """
        t0 = time.time()
        parsed = self._parser.parse(submission_path)
        full_text = parsed.full_text
        report = AnalysisReport(
            submission_path=submission_path,
            parsed_document=parsed,
        )

        # 1. N-gram similarity (always runs; no ML dependency)
        logger.info("Running n-gram detector...")
        if self._corpus_loaded:
            report.ngram_matches = self._ngram.find_matches(full_text)
        else:
            logger.warning("No corpus loaded; n-gram search skipped")

        # 2. Semantic similarity
        if self._semantic and self._corpus_loaded:
            logger.info("Running semantic detector...")
            try:
                report.semantic_matches = self._semantic.find_matches(full_text)
            except Exception as exc:
                logger.warning("Semantic detector failed: %s", exc)

        # 3. AI content detection
        if self._ai:
            logger.info("Running AI content detector...")
            try:
                report.ai_result = self._ai.detect(full_text)
                report.ai_score = report.ai_result.document_ensemble_score
            except Exception as exc:
                logger.warning("AI detector failed: %s", exc)

        # 4. Citation integrity
        if self._citation and parsed.references:
            logger.info("Verifying %d references...", len(parsed.references))
            try:
                report.citation_verdicts = self._citation.verify_references(
                    parsed.references)
                flagged = sum(
                    1 for v in report.citation_verdicts
                    if v.verdict in ("HALLUCINATED", "MISMATCH", "UNRESOLVABLE"))
                total = max(len(report.citation_verdicts), 1)
                report.citation_score = round(flagged / total, 3)
            except Exception as exc:
                logger.warning("Citation check failed: %s", exc)

        # 5. Stylometric analysis
        if self._stylo:
            logger.info("Running stylometric analyzer...")
            try:
                report.stylometric_result = self._stylo.analyze(
                    full_text, author_baseline=author_style_baseline)
                report.style_score = round(
                    1.0 - report.stylometric_result.consistency_score, 3)
            except Exception as exc:
                logger.warning("Stylometric analysis failed: %s", exc)

        # 6. Self-plagiarism
        if self._self_plag:
            logger.info("Running self-plagiarism detector...")
            try:
                report.self_plagiarism_result = self._self_plag.check_submission(
                    full_text)
                report.self_recycle_score = round(
                    report.self_plagiarism_result.overall_overlap_pct / 100.0, 3)
            except Exception as exc:
                logger.warning("Self-plagiarism detection failed: %s", exc)

        # 7. Aggregate plagiarism score
        report.plagiarism_score = self._aggregate_plagiarism_score(report)

        # 8. Overall risk and flags
        report.overall_risk, report.flags = self._assess_overall_risk(report)
        report.elapsed_seconds = round(time.time() - t0, 2)

        logger.info(
            "Analysis complete in %.1fs. Overall risk: %s",
            report.elapsed_seconds, report.overall_risk)
        return report

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _aggregate_plagiarism_score(self, report: AnalysisReport) -> float:
        """Combine n-gram and semantic signals into a 0-1 plagiarism score."""
        scores = []

        if report.ngram_matches:
            top_jaccard = report.ngram_matches[0].jaccard_estimate
            scores.append(min(top_jaccard * 2.0, 1.0))  # scale 0-1

        if report.semantic_matches:
            top_cosine = report.semantic_matches[0].cosine_score
            # cosine 0.82-1.0 maps to 0-1
            scores.append(min((top_cosine - 0.80) / 0.20, 1.0))

        return round(sum(scores) / len(scores), 3) if scores else 0.0

    def _assess_overall_risk(
        self, report: AnalysisReport
    ) -> tuple[str, list[str]]:
        flags: list[str] = []

        # Collect flags from individual detectors
        if report.stylometric_result:
            flags.extend(report.stylometric_result.flags)
        if report.ai_result:
            if report.ai_result.document_verdict in ("AI_LIKELY", "AI_DETECTED"):
                flags.append(
                    f"AI content detected: {report.ai_result.document_verdict} "
                    f"(score={report.ai_result.document_ensemble_score:.2f}, "
                    f"{report.ai_result.ai_fraction*100:.0f}% of paragraphs flagged)")
        if report.citation_verdicts:
            hallucinated = [v for v in report.citation_verdicts
                            if v.verdict == "HALLUCINATED"]
            mismatched = [v for v in report.citation_verdicts
                          if v.verdict == "MISMATCH"]
            if hallucinated:
                flags.append(
                    f"{len(hallucinated)} hallucinated citation(s) detected")
            if mismatched:
                flags.append(
                    f"{len(mismatched)} citation metadata mismatch(es)")
        if report.self_plagiarism_result:
            flags.extend(report.self_plagiarism_result.flags)
        if report.ngram_matches:
            high_j = [m for m in report.ngram_matches
                      if m.jaccard_estimate >= 0.50]
            if high_j:
                flags.append(
                    f"{len(high_j)} high-similarity n-gram match(es) "
                    f"(Jaccard >= 0.50)")
        if report.semantic_matches:
            paraphrases = [m for m in report.semantic_matches if m.is_paraphrase]
            if paraphrases:
                flags.append(
                    f"{len(paraphrases)} semantic paraphrase match(es) detected")

        # Determine overall risk level
        hallucinated_count = sum(
            1 for v in report.citation_verdicts if v.verdict == "HALLUCINATED")

        sp_risk = (report.self_plagiarism_result.risk_level
                   if report.self_plagiarism_result else "LOW")

        if (report.plagiarism_score > 0.70 or
                hallucinated_count > 0 or
                sp_risk == "CRITICAL"):
            risk = "CRITICAL"
        elif (report.plagiarism_score > 0.40 or
              report.ai_score > 0.70 or
              sp_risk == "HIGH" or
              report.citation_score > 0.30):
            risk = "HIGH"
        elif (report.plagiarism_score > 0.20 or
              report.ai_score > 0.50 or
              sp_risk == "MEDIUM" or
              report.citation_score > 0.10 or
              report.style_score > 0.30):
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return risk, flags
