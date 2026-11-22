"""
Watermark detector + risk-scoring safety tests.

Covers the fix for the bug where a keyless heuristic watermark verdict could
unconditionally force the overall integrity risk to CRITICAL. See
aegis/detectors/watermark_detector.py and aegis/core/pipeline.py.

Run with:  pytest tests/test_watermark.py -v
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _long_text(min_tokens: int = 200) -> str:
    """Deterministic text with >= min_tokens alphabetic word tokens."""
    words = ["consistent", "technical", "vocabulary", "phrase", "resolver",
             "anomaly", "detection", "isolation", "forest", "boundary"]
    text = []
    while len(text) < min_tokens + 10:
        text.extend(words)
    return " ".join(text)


def _make_report(watermark_result):
    from aegis.core.document import ParsedDocument
    from aegis.core.pipeline import AnalysisReport
    doc = ParsedDocument(
        path="x.txt", format="txt", title=None, authors=[], abstract=None,
        full_text="text", sections=[], references=[],
    )
    report = AnalysisReport(submission_path="x.txt", parsed_document=doc)
    report.watermark_result = watermark_result
    return report


def _minimal_pipeline(**overrides):
    from aegis.core.pipeline import AEGISPipeline, PipelineConfig
    cfg = PipelineConfig(
        run_ai_detector=False,
        run_semantic=False,
        run_citation_check=False,
        run_stylometric=False,
        run_self_plagiarism=False,
        run_citation_network=False,
        run_coherence_analyzer=False,
        **overrides,
    )
    return AEGISPipeline(config=cfg)


# ---------------------------------------------------------------------------
# Detector modes
# ---------------------------------------------------------------------------

class TestWatermarkModes:

    def test_disabled_mode_returns_skipped(self):
        from aegis.detectors.watermark_detector import (
            LLMWatermarkDetector, WatermarkMode, DetectorExecutionStatus)
        det = LLMWatermarkDetector(mode=WatermarkMode.DISABLED)
        result = det.detect(_long_text())
        assert result.status == DetectorExecutionStatus.SKIPPED
        assert result.verdict == "SKIPPED"
        assert result.affects_overall_risk is False
        assert result.evidence_status == "not_evaluated"

    def test_verified_scheme_without_backend_is_rejected_not_silently_downgraded(self):
        from aegis.detectors.watermark_detector import (
            LLMWatermarkDetector, WatermarkMode, DetectorExecutionStatus)
        det = LLMWatermarkDetector(mode=WatermarkMode.VERIFIED_SCHEME, watermark_scheme="kgw")
        result = det.detect(_long_text())
        assert result.status == DetectorExecutionStatus.UNAVAILABLE
        assert result.verdict == "UNSUPPORTED_CONFIGURATION"
        assert result.affects_overall_risk is False
        assert result.configuration_validated is False
        # Must not silently behave like EXPERIMENTAL (no z_score/entropy computed).
        assert result.z_score is None

    def test_insufficient_text_abstains_with_reason(self):
        from aegis.detectors.watermark_detector import LLMWatermarkDetector, WatermarkMode
        det = LLMWatermarkDetector(mode=WatermarkMode.EXPERIMENTAL, min_tokens=200)
        result = det.detect("only a few real words here")
        assert result.verdict == "INSUFFICIENT_TEXT"
        assert result.affects_overall_risk is False
        assert result.tokens_evaluated < 200
        assert result.warnings

    def test_experimental_never_sets_affects_overall_risk(self):
        from aegis.detectors.watermark_detector import LLMWatermarkDetector, WatermarkMode
        det = LLMWatermarkDetector(mode=WatermarkMode.EXPERIMENTAL, min_tokens=200)
        result = det.detect(_long_text())
        assert result.affects_overall_risk is False
        assert result.evidence_status == "experimental"

    def test_experimental_cannot_return_definitive_watermark_claim(self):
        from aegis.detectors.watermark_detector import LLMWatermarkDetector, WatermarkMode
        det = LLMWatermarkDetector(mode=WatermarkMode.EXPERIMENTAL, min_tokens=200)
        result = det.detect(_long_text())
        assert result.verdict in ("STATISTICAL_ANOMALY", "NO_STATISTICAL_ANOMALY")
        assert result.verdict != "WATERMARKED"

    def test_detector_failure_does_not_affect_risk(self, monkeypatch):
        from aegis.detectors.watermark_detector import LLMWatermarkDetector, WatermarkMode
        det = LLMWatermarkDetector(mode=WatermarkMode.EXPERIMENTAL, min_tokens=200)
        monkeypatch.setattr(
            det, "_kirchenbauer_z_score",
            lambda tokens: (_ for _ in ()).throw(ValueError("boom")))
        result = det.detect(_long_text())
        assert result.verdict == "ANALYSIS_FAILED"
        assert result.affects_overall_risk is False
        assert result.error_code == "ANALYSIS_EXCEPTION"


# ---------------------------------------------------------------------------
# Numerical correctness of the z-test survival function
# ---------------------------------------------------------------------------

class TestNormalSurvivalFunction:

    def test_known_critical_values(self):
        from aegis.detectors.watermark_detector import _norm_sf
        assert _norm_sf(0.0) == pytest.approx(0.5, abs=1e-6)
        assert _norm_sf(1.6448536) == pytest.approx(0.05, abs=1e-4)
        assert _norm_sf(1.9599640) == pytest.approx(0.025, abs=1e-4)
        assert _norm_sf(2.5758293) == pytest.approx(0.005, abs=1e-4)
        # Survival function is antisymmetric around 0.5.
        assert _norm_sf(-1.6448536) == pytest.approx(1 - 0.05, abs=1e-4)


# ---------------------------------------------------------------------------
# Pipeline risk-scoring behavior
# ---------------------------------------------------------------------------

class TestPipelineRiskScoring:

    def test_experimental_anomaly_alone_does_not_force_critical(self):
        from aegis.detectors.watermark_detector import (
            WatermarkResult, WatermarkMode, DetectorExecutionStatus)
        wr = WatermarkResult(
            status=DetectorExecutionStatus.COMPLETED,
            mode=WatermarkMode.EXPERIMENTAL,
            verdict="STATISTICAL_ANOMALY",
            evidence_status="experimental",
            affects_overall_risk=False,
        )
        pipeline = _minimal_pipeline()
        risk, flags = pipeline._assess_overall_risk(_make_report(wr))
        assert risk == "LOW"
        assert any("Experimental" in f and "does not affect" in f for f in flags)

    def test_unsupported_configuration_does_not_affect_risk(self):
        from aegis.detectors.watermark_detector import (
            WatermarkResult, WatermarkMode, DetectorExecutionStatus)
        wr = WatermarkResult(
            status=DetectorExecutionStatus.UNAVAILABLE,
            mode=WatermarkMode.VERIFIED_SCHEME,
            verdict="UNSUPPORTED_CONFIGURATION",
            evidence_status="failed",
            affects_overall_risk=False,
        )
        pipeline = _minimal_pipeline()
        risk, _flags = pipeline._assess_overall_risk(_make_report(wr))
        assert risk == "LOW"

    def test_validated_scheme_signal_raises_risk_by_at_most_one_level(self):
        from aegis.detectors.watermark_detector import (
            WatermarkResult, WatermarkMode, DetectorExecutionStatus)
        wr = WatermarkResult(
            status=DetectorExecutionStatus.COMPLETED,
            mode=WatermarkMode.VERIFIED_SCHEME,
            verdict="VERIFIED_SCHEME_SIGNAL",
            evidence_status="scheme_verified",
            affects_overall_risk=True,
            watermark_scheme="kgw",
            configuration_validated=True,
        )
        pipeline = _minimal_pipeline(watermark_max_risk_increase_levels=1)
        risk, flags = pipeline._assess_overall_risk(_make_report(wr))
        assert risk == "MEDIUM"  # LOW -> MEDIUM, exactly one level
        assert any("Verified watermark" in f for f in flags)

    def test_validated_scheme_signal_cannot_force_critical_from_low(self):
        # Even if misconfigured to a large value, a single watermark signal
        # must never be able to jump straight to CRITICAL from LOW.
        from aegis.detectors.watermark_detector import (
            WatermarkResult, WatermarkMode, DetectorExecutionStatus)
        wr = WatermarkResult(
            status=DetectorExecutionStatus.COMPLETED,
            mode=WatermarkMode.VERIFIED_SCHEME,
            verdict="VERIFIED_SCHEME_SIGNAL",
            evidence_status="scheme_verified",
            affects_overall_risk=True,
            watermark_scheme="kgw",
            configuration_validated=True,
        )
        pipeline = _minimal_pipeline(watermark_max_risk_increase_levels=5)
        risk, _flags = pipeline._assess_overall_risk(_make_report(wr))
        assert risk != "CRITICAL"
        assert risk == "MEDIUM"

    def test_no_watermark_result_is_a_noop(self):
        pipeline = _minimal_pipeline()
        risk, flags = pipeline._assess_overall_risk(_make_report(None))
        assert risk == "LOW"
        assert not any("watermark" in f.lower() for f in flags)


# ---------------------------------------------------------------------------
# Report generator wiring
# ---------------------------------------------------------------------------

class TestReportGeneratorWatermarkSection:

    def test_experimental_result_serializes_and_renders(self, tmp_path):
        from aegis.report.generator import ReportGenerator
        from aegis.detectors.watermark_detector import (
            WatermarkResult, WatermarkMode, DetectorExecutionStatus)

        wr = WatermarkResult(
            status=DetectorExecutionStatus.COMPLETED,
            mode=WatermarkMode.EXPERIMENTAL,
            verdict="NO_STATISTICAL_ANOMALY",
            evidence_status="experimental",
            affects_overall_risk=False,
        )
        report = _make_report(wr)
        gen = ReportGenerator(str(tmp_path))
        data = gen._report_to_dict(report)

        assert data["watermark"]["mode"] == "experimental"
        assert data["watermark"]["affects_overall_risk"] is False

        html = gen._render_html(data, report)
        assert "LLM Watermark Analysis" in html

    def test_skipped_result_never_shows_experimental_badge(self, tmp_path):
        from aegis.report.generator import ReportGenerator
        from aegis.detectors.watermark_detector import (
            WatermarkResult, WatermarkMode, DetectorExecutionStatus)

        wr = WatermarkResult(
            status=DetectorExecutionStatus.SKIPPED,
            mode=WatermarkMode.DISABLED,
            verdict="SKIPPED",
            evidence_status="not_evaluated",
            affects_overall_risk=False,
        )
        report = _make_report(wr)
        gen = ReportGenerator(str(tmp_path))
        data = gen._report_to_dict(report)
        html = gen._render_html(data, report)
        assert "EXPERIMENTAL</span>" not in html
