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
  8. LLM watermark detection (Kirchenbauer z-test; soft watermark entropy)
  9. Citation network analysis (self-citation inflation; predatory journals)
 10. Semantic coherence analysis (discourse connectors; sentence uniformity)
 11. Target-publisher verification (IEEE/ACM/Elsevier/IET/IETE/BCS-scoped
     citation-claim checks and duplicate-submission search via Crossref)
 12. Mathematical formula checking (equation numbering/reference integrity,
     notation conventions -- offline, no ML dependency)
 13. Grammar & language convention checking (contractions, US/UK spelling
     consistency, subject/verb agreement, usage -- offline, no ML dependency)
 14. Per-venue guideline compliance (IEEE/ACM/BCS/IET/ISACA, checked
     SEPARATELY -- opt-in via PipelineConfig.guideline_venues)

Each detector runs independently; results are merged into AnalysisReport.
Detectors 12-14 are compliance/quality signals, not misconduct signals:
they are reported for visibility but never feed into overall_risk (see
_assess_overall_risk) -- bad grammar or a nonstandard equation reference
is not evidence of academic misconduct.
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
from aegis.detectors.watermark_detector import (
    LLMWatermarkDetector, WatermarkResult, WatermarkMode)
from aegis.detectors.citation_network import CitationNetworkAnalyzer, CitationNetworkResult
from aegis.detectors.coherence_analyzer import SemanticCoherenceAnalyzer, CoherenceResult
from aegis.detectors.venue_verification import TargetPublisherVerifier, VenueVerificationResult
from aegis.detectors.publisher_registry import DEFAULT_TARGET_PUBLISHERS
from aegis.detectors.math_formula import MathFormulaChecker, MathAnalysisResult
from aegis.detectors.grammar import GrammarLanguageChecker, GrammarAnalysisResult
from aegis.guidelines.checker import GuidelineComplianceChecker, GuidelineComplianceResult

logger = logging.getLogger(__name__)

_RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


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

    # Watermark detector (v2.0)
    watermark_mode: WatermarkMode = WatermarkMode.EXPERIMENTAL
    watermark_z_threshold: float = 4.0
    watermark_z_suspicious: float = 2.5
    watermark_min_tokens: int = 200
    # Only ever applied when a WatermarkResult sets affects_overall_risk=True
    # (currently only reachable by a validated VERIFIED_SCHEME run, which is
    # not yet implemented). EXPERIMENTAL results never reach this path.
    watermark_max_risk_increase_levels: int = 1

    # Citation network analyzer (v2.0)
    citation_network_self_cite_threshold: float = 0.30
    citation_network_missing_doi_threshold: float = 0.60
    citation_network_use_openalex: bool = True
    citation_network_offline: bool = False

    # Coherence analyzer (v2.0)
    coherence_connector_threshold: float = 3.5
    coherence_cv_threshold: float = 0.35
    coherence_hedge_threshold: float = 2.5

    # Target-publisher verification (v2.4)
    venue_target_publishers: tuple[str, ...] = DEFAULT_TARGET_PUBLISHERS
    venue_title_similarity_threshold: float = 0.75
    venue_offline: bool = False

    # Grammar & language checker (v3.0) -- pure-Python + optional spaCy
    grammar_long_sentence_words: int = 45
    grammar_use_spacy: bool = True

    # Per-venue guideline compliance (v3.0) -- opt-in; empty tuple = skip.
    # Populate with e.g. ("IEEE", "ACM", "BCS", "IET", "ISACA") to run all
    # five SEPARATELY (each gets its own GuidelineComplianceResult).
    guideline_venues: tuple[str, ...] = ()

    # Runtime
    device: str = "cpu"
    run_ai_detector: bool = True
    run_citation_check: bool = True
    run_semantic: bool = True
    run_stylometric: bool = True
    run_self_plagiarism: bool = True
    run_watermark_detector: bool = True
    run_citation_network: bool = True
    run_coherence_analyzer: bool = True
    run_venue_verification: bool = True
    run_math_check: bool = True
    run_grammar_check: bool = True


@dataclass
class AnalysisReport:
    submission_path: str
    parsed_document: ParsedDocument

    # Detector results (None if detector was skipped)
    ngram_matches: list[NGramMatch] = field(default_factory=list)
    semantic_matches: list[SemanticMatch] = field(default_factory=list)
    ai_result: Optional[AIDetectionResult] = None
    citation_verdicts: list[CitationVerdict] = field(default_factory=list)
    # Coverage/assessment metadata from CitationIntegrityDetector.summary():
    # total references, how many were independently verified, and whether
    # the sample is large enough for a percentage-based verdict to be
    # meaningful (see MIN_REFERENCES_FOR_ASSESSMENT).
    citation_summary: dict = field(default_factory=dict)
    stylometric_result: Optional[StyleAnalysisResult] = None
    self_plagiarism_result: Optional[SelfPlagiarismResult] = None

    # v2.0 detector results
    watermark_result: Optional[WatermarkResult] = None
    citation_network_result: Optional[CitationNetworkResult] = None
    coherence_result: Optional[CoherenceResult] = None
    venue_verification_result: Optional[VenueVerificationResult] = None

    # v3.0 results -- compliance/quality signals, never part of overall_risk
    math_result: Optional[MathAnalysisResult] = None
    grammar_result: Optional[GrammarAnalysisResult] = None
    guideline_results: dict[str, GuidelineComplianceResult] = field(default_factory=dict)

    # Aggregate risk scores (0.0 - 1.0)
    plagiarism_score: float = 0.0    # combined n-gram + semantic
    ai_score: float = 0.0            # from AI detector ensemble
    citation_score: float = 0.0      # fraction of flagged citations
    style_score: float = 0.0         # style inconsistency score
    self_recycle_score: float = 0.0  # recycling overlap percentage / 100
    watermark_score: float = 0.0     # watermark detection confidence
    coherence_score: float = 0.0     # AI coherence signal

    # Final verdict
    overall_risk: str = "UNKNOWN"   # LOW | MEDIUM | HIGH | CRITICAL
    flags: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    # Privacy disclosure: which external services (if any) this specific run
    # actually contacted. Document content is never sent anywhere; only
    # citation metadata (titles/authors/DOIs) can leave the machine, and only
    # when citation checking runs in online mode.
    network_activity: dict = field(default_factory=dict)

    # Per-detector execution status: {"status": "completed"|"disabled"|
    # "unavailable"|"failed", "reason": str|None}. A score of 0.0 is
    # ambiguous on its own -- it means both "ran and found nothing" and
    # "didn't run at all" unless this is checked too.
    detector_status: dict = field(default_factory=dict)


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

        self._watermark = LLMWatermarkDetector(
            mode=self.cfg.watermark_mode,
            z_threshold=self.cfg.watermark_z_threshold,
            z_suspicious=self.cfg.watermark_z_suspicious,
            min_tokens=self.cfg.watermark_min_tokens,
        ) if self.cfg.run_watermark_detector else None

        self._citation_network = CitationNetworkAnalyzer(
            self_citation_threshold=self.cfg.citation_network_self_cite_threshold,
            missing_doi_threshold=self.cfg.citation_network_missing_doi_threshold,
            use_openalex=self.cfg.citation_network_use_openalex,
            offline=self.cfg.citation_network_offline,
        ) if self.cfg.run_citation_network else None

        self._coherence = SemanticCoherenceAnalyzer(
            connector_threshold=self.cfg.coherence_connector_threshold,
            cv_threshold=self.cfg.coherence_cv_threshold,
            hedge_threshold=self.cfg.coherence_hedge_threshold,
        ) if self.cfg.run_coherence_analyzer else None

        self._venue_verifier = TargetPublisherVerifier(
            target_publishers=list(self.cfg.venue_target_publishers),
            email=self.cfg.citation_email,
            title_similarity_threshold=self.cfg.venue_title_similarity_threshold,
            offline=self.cfg.venue_offline,
        ) if self.cfg.run_venue_verification else None

        self._math_checker = MathFormulaChecker() if self.cfg.run_math_check else None

        self._grammar_checker = GrammarLanguageChecker(
            use_spacy=self.cfg.grammar_use_spacy,
            long_sentence_words=self.cfg.grammar_long_sentence_words,
        ) if self.cfg.run_grammar_check else None

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
        # Plagiarism similarity (n-gram/semantic) must run on body text only.
        # A correctly-formatted citation to a real paper necessarily reproduces
        # that paper's own title/author string near-verbatim, so scanning the
        # References section against an indexed corpus of other papers'
        # reference lists flags routine bibliographic overlap as "plagiarism."
        # See ParsedDocument.body_text.
        plagiarism_text = parsed.body_text
        report = AnalysisReport(
            submission_path=submission_path,
            parsed_document=parsed,
        )

        def _status(name: str, status: str, reason: Optional[str] = None) -> None:
            report.detector_status[name] = {"status": status, "reason": reason}

        # 1. N-gram similarity (always runs; no ML dependency, no on/off config)
        if not self._corpus_loaded:
            logger.warning("No corpus loaded; n-gram search skipped")
            _status("ngram", "unavailable", "no comparison corpus loaded")
        else:
            logger.info("Running n-gram detector...")
            try:
                report.ngram_matches = self._ngram.find_matches(plagiarism_text)
                _status("ngram", "completed")
            except Exception as exc:
                logger.warning("N-gram detector failed: %s", exc)
                _status("ngram", "failed", str(exc))

        # 2. Semantic similarity
        if not self._semantic:
            _status("semantic", "disabled")
        elif not self._corpus_loaded:
            _status("semantic", "unavailable", "no comparison corpus loaded")
        else:
            logger.info("Running semantic detector...")
            try:
                report.semantic_matches = self._semantic.find_matches(plagiarism_text)
                _status("semantic", "completed")
            except Exception as exc:
                logger.warning("Semantic detector failed: %s", exc)
                _status("semantic", "failed", str(exc))

        # 3. AI content detection
        if not self._ai:
            _status("ai_content", "disabled")
        else:
            logger.info("Running AI content detector...")
            try:
                report.ai_result = self._ai.detect(full_text)
                report.ai_score = report.ai_result.document_ensemble_score
                _status("ai_content", "completed")
            except Exception as exc:
                logger.warning("AI detector failed: %s", exc)
                _status("ai_content", "failed", str(exc))

        # 4. Citation integrity
        if not self._citation:
            _status("citation", "disabled")
        elif not parsed.references:
            _status("citation", "unavailable", "no references detected in document")
        else:
            logger.info("Verifying %d references...", len(parsed.references))
            try:
                report.citation_verdicts = self._citation.verify_references(
                    parsed.references)
                # citation_score (and the risk levels derived from it) must
                # only reflect confirmed integrity problems (HALLUCINATED /
                # MISMATCH), never verdicts that just mean "could not verify"
                # (UNRESOLVABLE / UNAVAILABLE / NO_DOI / NOT_FOUND_IN_CROSSREF)
                # -- a network hiccup or an unfamiliar registration agency is
                # not evidence of a fabricated citation.
                report.citation_summary = self._citation.summary(report.citation_verdicts)
                report.citation_score = report.citation_summary["citation_integrity_score"]
                report.citation_score = round(1.0 - report.citation_score, 3)
                _status("citation", "completed")
            except Exception as exc:
                logger.warning("Citation check failed: %s", exc)
                _status("citation", "failed", str(exc))

        # 5. Stylometric analysis
        if not self._stylo:
            _status("stylometric", "disabled")
        else:
            logger.info("Running stylometric analyzer...")
            try:
                report.stylometric_result = self._stylo.analyze(
                    full_text, author_baseline=author_style_baseline)
                report.style_score = round(
                    1.0 - report.stylometric_result.consistency_score, 3)
                _status("stylometric", "completed")
            except Exception as exc:
                logger.warning("Stylometric analysis failed: %s", exc)
                _status("stylometric", "failed", str(exc))

        # 6. Self-plagiarism
        if not self._self_plag:
            _status("self_plagiarism", "disabled")
        elif not self._self_plag._corpus_index:
            _status("self_plagiarism", "unavailable", "no prior works loaded")
        else:
            logger.info("Running self-plagiarism detector...")
            try:
                report.self_plagiarism_result = self._self_plag.check_submission(
                    full_text)
                report.self_recycle_score = round(
                    report.self_plagiarism_result.overall_overlap_pct / 100.0, 3)
                _status("self_plagiarism", "completed")
            except Exception as exc:
                logger.warning("Self-plagiarism detection failed: %s", exc)
                _status("self_plagiarism", "failed", str(exc))

        # 7. Aggregate plagiarism score
        report.plagiarism_score = self._aggregate_plagiarism_score(report)

        # 8. LLM watermark detection
        if not self._watermark:
            _status("watermark", "disabled")
        else:
            logger.info("Running LLM watermark detector...")
            try:
                report.watermark_result = self._watermark.detect(full_text)
                wr = report.watermark_result
                report.watermark_score = (
                    wr.confidence if wr.evidence_status in ("experimental", "scheme_verified") else 0.0
                )
                _status(
                    "watermark",
                    {"completed": "completed", "skipped": "disabled",
                     "unavailable": "unavailable", "failed": "failed"}.get(
                        wr.status.value, "completed"),
                    wr.error_code,
                )
            except Exception as exc:
                logger.warning("Watermark detector failed: %s", exc)
                _status("watermark", "failed", str(exc))

        # 9. Citation network analysis
        if not self._citation_network:
            _status("citation_network", "disabled")
        elif not report.citation_verdicts:
            _status("citation_network", "unavailable", "no verified references to analyze")
        else:
            logger.info("Running citation network analysis...")
            try:
                submission_authors = []
                if parsed.metadata:
                    submission_authors = parsed.metadata.get("authors", [])
                self._citation_network.submission_authors = [
                    a.lower() for a in submission_authors
                ]
                report.citation_network_result = self._citation_network.analyze(
                    report.citation_verdicts)
                _status("citation_network", "completed")
            except Exception as exc:
                logger.warning("Citation network analysis failed: %s", exc)
                _status("citation_network", "failed", str(exc))

        # 10. Semantic coherence analysis
        if not self._coherence:
            _status("coherence", "disabled")
        else:
            logger.info("Running coherence analyzer...")
            try:
                report.coherence_result = self._coherence.analyze(full_text)
                report.coherence_score = report.coherence_result.ensemble_score
                _status("coherence", "completed")
            except Exception as exc:
                logger.warning("Coherence analysis failed: %s", exc)
                _status("coherence", "failed", str(exc))

        # 11. Target-publisher verification (IEEE/ACM/Elsevier/IET/IETE/BCS)
        if not self._venue_verifier:
            _status("venue_verification", "disabled")
        else:
            logger.info("Running target-publisher verification...")
            try:
                report.venue_verification_result = self._venue_verifier.analyze(
                    parsed.title, report.citation_verdicts)
                _status("venue_verification", "completed")
            except Exception as exc:
                logger.warning("Target-publisher verification failed: %s", exc)
                _status("venue_verification", "failed", str(exc))

        # 12. Mathematical formula checking (compliance signal; never
        # affects overall_risk)
        if not self._math_checker:
            _status("math_check", "disabled")
        else:
            logger.info("Running math formula checker...")
            try:
                report.math_result = self._math_checker.analyze(
                    submission_path, parsed.format, full_text)
                _status("math_check", "completed")
            except Exception as exc:
                logger.warning("Math formula checker failed: %s", exc)
                _status("math_check", "failed", str(exc))

        # 13. Grammar & language convention checking (compliance signal;
        # never affects overall_risk)
        if not self._grammar_checker:
            _status("grammar_check", "disabled")
        else:
            logger.info("Running grammar & language checker...")
            try:
                report.grammar_result = self._grammar_checker.analyze(parsed.body_text)
                _status("grammar_check", "completed")
            except Exception as exc:
                logger.warning("Grammar checker failed: %s", exc)
                _status("grammar_check", "failed", str(exc))

        # 14. Per-venue guideline compliance (opt-in; runs each requested
        # venue SEPARATELY -- see aegis.guidelines)
        if not self.cfg.guideline_venues:
            _status("guideline_compliance", "disabled")
        else:
            logger.info("Running guideline compliance for: %s",
                        ", ".join(self.cfg.guideline_venues))
            try:
                checker = GuidelineComplianceChecker(
                    math_result=report.math_result,
                    grammar_result=report.grammar_result,
                    full_text=full_text,
                    word_count=parsed.word_count,
                )
                report.guideline_results = checker.check_all(list(self.cfg.guideline_venues))
                _status("guideline_compliance", "completed")
            except Exception as exc:
                logger.warning("Guideline compliance check failed: %s", exc)
                _status("guideline_compliance", "failed", str(exc))

        # 15. Overall risk and flags
        report.overall_risk, report.flags = self._assess_overall_risk(report)
        report.elapsed_seconds = round(time.time() - t0, 2)

        contacted = []
        citation_online = (
            self.cfg.run_citation_check and not self.cfg.citation_offline
            and len(report.citation_verdicts) > 0
        )
        if citation_online:
            contacted.append("Crossref")
        if (report.citation_network_result
                and report.citation_network_result.openalex_queried):
            contacted.append("OpenAlex")
        if (report.venue_verification_result
                and report.venue_verification_result.queried
                and "Crossref" not in contacted):
            contacted.append("Crossref")
        report.network_activity = {
            "document_content_transmitted": False,
            "citation_check_mode": (
                "offline" if self.cfg.citation_offline
                else "online" if self.cfg.run_citation_check
                else "disabled"
            ),
            "citation_network_mode": (
                "offline" if self.cfg.citation_network_offline
                else "online" if self.cfg.run_citation_network
                else "disabled"
            ),
            "external_services_contacted": contacted,
        }

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

        # v2.0 detector flags
        if report.watermark_result:
            wr = report.watermark_result
            if wr.verdict == "STATISTICAL_ANOMALY":
                flags.append(
                    f"[Experimental] Watermark heuristic flagged a token-distribution "
                    f"anomaly (z={wr.z_score}, confidence={wr.confidence:.0%}). "
                    f"Not proof of a watermark or AI generation; does not affect "
                    f"the overall risk score."
                )
            elif wr.verdict == "UNSUPPORTED_CONFIGURATION":
                flags.append(
                    "[Watermark] VERIFIED_SCHEME mode was requested but no "
                    "known-scheme verifier is implemented; no watermark "
                    "evidence was produced."
                )

        if report.citation_network_result:
            for net_flag in report.citation_network_result.flags:
                if net_flag.severity in ("HIGH", "MEDIUM"):
                    flags.append(f"[Citation Network] {net_flag.message}")

        if report.venue_verification_result:
            for v_flag in report.venue_verification_result.flags:
                if v_flag.severity in ("HIGH", "MEDIUM"):
                    flags.append(f"[{v_flag.flag_type}] {v_flag.message}")

        if report.coherence_result and report.coherence_result.verdict in (
            "AI_POLISHED", "AI_GENERATED"
        ):
            flags.append(
                f"AI-polished writing detected: coherence score "
                f"{report.coherence_result.ensemble_score:.2f} "
                f"({report.coherence_result.verdict})"
            )

        # Determine overall risk level.
        #
        # Citation findings only get to influence risk when the sample is
        # large enough for a percentage (or a hallucination count) to mean
        # anything -- CitationIntegrityDetector.summary() marks the
        # assessment INCONCLUSIVE below MIN_REFERENCES_FOR_ASSESSMENT
        # references or MIN_COVERAGE_FOR_ASSESSMENT verification coverage.
        # Without this gate, a single false HALLUCINATED verdict out of one
        # detected reference reads as "100% of citations are fabricated" and
        # forces CRITICAL on its own -- exactly the failure mode this guards
        # against. citation_summary defaults to {} when citation checking
        # didn't run, in which case citation_score is already 0.0 and this
        # gate has no effect either way.
        citation_reliable = report.citation_summary.get("assessment") != "INCONCLUSIVE"
        hallucinated_count = (
            sum(1 for v in report.citation_verdicts if v.verdict == "HALLUCINATED")
            if citation_reliable else 0
        )
        citation_score_for_risk = report.citation_score if citation_reliable else 0.0
        if not citation_reliable and report.citation_summary:
            flags.append(
                "Citation assessment: INCONCLUSIVE "
                f"({report.citation_summary.get('total_references', 0)} reference(s), "
                f"{report.citation_summary.get('verification_coverage', 0.0):.0%} verified) "
                "-- too few references or too little verification coverage for a "
                "percentage-based citation risk to be meaningful; citation findings "
                "are not factored into the overall risk level."
            )

        sp_risk = (report.self_plagiarism_result.risk_level
                   if report.self_plagiarism_result else "LOW")

        network_risk = (report.citation_network_result.overall_risk
                        if report.citation_network_result else "LOW")

        # Like citation_network_result, venue_verification never forces
        # CRITICAL on its own -- a single venue-claim mismatch or duplicate-
        # title hit is a lead for human review, not proof of misconduct.
        venue_risk = (report.venue_verification_result.overall_risk
                      if report.venue_verification_result else "LOW")

        if (report.plagiarism_score > 0.70 or
                hallucinated_count > 0 or
                sp_risk == "CRITICAL"):
            risk = "CRITICAL"
        elif (report.plagiarism_score > 0.40 or
              report.ai_score > 0.70 or
              sp_risk == "HIGH" or
              citation_score_for_risk > 0.30 or
              network_risk == "HIGH" or
              venue_risk == "HIGH" or
              report.coherence_score > 0.75):
            risk = "HIGH"
        elif (report.plagiarism_score > 0.20 or
              report.ai_score > 0.50 or
              sp_risk == "MEDIUM" or
              citation_score_for_risk > 0.10 or
              report.style_score > 0.30 or
              network_risk == "MEDIUM" or
              venue_risk == "MEDIUM" or
              report.coherence_score > 0.50):
            risk = "MEDIUM"
        else:
            risk = "LOW"

        # A watermark signal may only ever raise risk by a configurable,
        # capped number of levels, and only once the detector itself has
        # validated a known scheme (affects_overall_risk=True). It can never
        # independently force CRITICAL. EXPERIMENTAL and UNSUPPORTED_CONFIGURATION
        # results always have affects_overall_risk=False and never reach here.
        if report.watermark_result and report.watermark_result.affects_overall_risk:
            wr = report.watermark_result
            current_idx = _RISK_LEVELS.index(risk)
            increase = max(0, min(1, self.cfg.watermark_max_risk_increase_levels))
            new_idx = min(len(_RISK_LEVELS) - 1, current_idx + increase)
            if new_idx > current_idx:
                risk = _RISK_LEVELS[new_idx]
                flags.append(
                    f"[Verified watermark] Validated signal for scheme="
                    f"{wr.watermark_scheme!r} raised risk by one level. This is "
                    f"provenance evidence, requires manual review, and does not "
                    f"by itself establish academic misconduct."
                )

        # Math/grammar compliance flags are appended AFTER risk is final --
        # they are quality/style signals, not misconduct signals, and must
        # never move the LOW/MEDIUM/HIGH/CRITICAL verdict computed above.
        if report.math_result:
            flags.extend(report.math_result.flags)
        if report.grammar_result:
            flags.extend(report.grammar_result.flags)

        return risk, flags
