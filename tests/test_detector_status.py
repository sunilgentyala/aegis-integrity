"""
Tests for per-detector execution status tracking.

Previously a score of 0.0 (or an empty result) was ambiguous: it could mean
"detector ran and found nothing," "detector was disabled," "no corpus was
loaded so there was nothing to compare against," or "the detector raised an
exception that got logged and silently swallowed." report.detector_status
now distinguishes all four cases per detector.
"""

from unittest.mock import patch

from aegis.core.pipeline import AEGISPipeline, PipelineConfig

SAMPLE_TEXT_WITH_REFS = """
Introduction

This paper studies network security monitoring approaches for enterprise
DNS infrastructure and presents a novel anomaly detection pipeline that
operates entirely within the enterprise perimeter without external calls.

References

[1] J. Smith, "A study of DNS anomalies," Journal of Security, 2021.
[2] A. Lee, "Deep learning for intrusion detection," IEEE Trans., 2022.
"""

SAMPLE_TEXT_NO_REFS = """
Introduction

This paper studies network security monitoring approaches for enterprise
DNS infrastructure and presents a novel anomaly detection pipeline.
"""


def _all_heavy_detectors_disabled_config(**overrides):
    cfg_kwargs = dict(
        run_ai_detector=False, run_semantic=False, run_stylometric=False,
        run_self_plagiarism=False, run_watermark_detector=False,
        run_citation_network=False, run_coherence_analyzer=False,
        run_citation_check=False,
    )
    cfg_kwargs.update(overrides)
    return PipelineConfig(**cfg_kwargs)


class TestDetectorStatusDisabledVsUnavailable:

    def test_disabled_detectors_report_disabled_status(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_WITH_REFS, encoding="utf-8")
        report = AEGISPipeline(config=_all_heavy_detectors_disabled_config()).analyze(str(path))

        for name in ("semantic", "ai_content", "citation", "stylometric",
                     "self_plagiarism", "watermark", "citation_network", "coherence"):
            assert report.detector_status[name]["status"] == "disabled", (
                f"{name} should be 'disabled', got {report.detector_status[name]}"
            )

    def test_ngram_unavailable_without_corpus(self, tmp_path):
        """N-gram has no on/off config flag -- it's either run (corpus
        loaded) or unavailable (no corpus), never 'disabled'."""
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_WITH_REFS, encoding="utf-8")
        report = AEGISPipeline(config=_all_heavy_detectors_disabled_config()).analyze(str(path))
        assert report.detector_status["ngram"]["status"] == "unavailable"
        assert "corpus" in report.detector_status["ngram"]["reason"]

    def test_citation_unavailable_when_no_references_detected(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_NO_REFS, encoding="utf-8")
        cfg = _all_heavy_detectors_disabled_config(
            run_citation_check=True, citation_offline=True)
        report = AEGISPipeline(config=cfg).analyze(str(path))
        assert report.detector_status["citation"]["status"] == "unavailable"
        assert "references" in report.detector_status["citation"]["reason"]

    def test_citation_completed_when_references_present(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_WITH_REFS, encoding="utf-8")
        cfg = _all_heavy_detectors_disabled_config(
            run_citation_check=True, citation_offline=True)
        report = AEGISPipeline(config=cfg).analyze(str(path))
        assert report.detector_status["citation"]["status"] == "completed"

    def test_self_plagiarism_unavailable_without_prior_works(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_NO_REFS, encoding="utf-8")
        cfg = _all_heavy_detectors_disabled_config(
            run_self_plagiarism=True, use_sbert_self_plagiarism=False)
        pipeline = AEGISPipeline(config=cfg)
        # No load_prior_works() call -- corpus stays empty.
        report = pipeline.analyze(str(path))
        assert report.detector_status["self_plagiarism"]["status"] == "unavailable"
        assert "prior works" in report.detector_status["self_plagiarism"]["reason"]

    def test_self_plagiarism_completed_with_prior_works_loaded(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_NO_REFS, encoding="utf-8")
        cfg = _all_heavy_detectors_disabled_config(
            run_self_plagiarism=True, use_sbert_self_plagiarism=False)
        pipeline = AEGISPipeline(config=cfg)
        pipeline.load_prior_works([("prior1", SAMPLE_TEXT_NO_REFS * 3)])
        report = pipeline.analyze(str(path))
        assert report.detector_status["self_plagiarism"]["status"] == "completed"


class TestDetectorStatusFailure:

    def test_detector_exception_reports_failed_not_silently_clean(self, tmp_path):
        """A detector that raises must show up as 'failed', not look
        identical to a clean 'completed' result with a 0.0 score."""
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_NO_REFS, encoding="utf-8")
        cfg = _all_heavy_detectors_disabled_config(run_stylometric=True)
        pipeline = AEGISPipeline(config=cfg)

        with patch.object(pipeline._stylo, "analyze", side_effect=RuntimeError("boom")):
            report = pipeline.analyze(str(path))

        assert report.detector_status["stylometric"]["status"] == "failed"
        assert "boom" in report.detector_status["stylometric"]["reason"]
        assert report.stylometric_result is None
