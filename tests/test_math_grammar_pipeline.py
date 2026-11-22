"""
Pipeline-wiring tests for the math/grammar/guideline-compliance detectors
(v3.0). Mirrors the pattern in test_venue_verification.py's
TestPipelineWiring -- these are compliance/quality signals and must never
influence overall_risk.
"""

from aegis.core.pipeline import AEGISPipeline, PipelineConfig

SAMPLE_TEXT = """
Introduction

We colour the graph using a behaviour-based heuristic. It's a well-known
analyse of the system. The data is collected from ten sensors.

E = mc^2 (1)
F = ma (3)

As shown in (1), the relation holds. Using (9), we extend the result.
"""


def _fast_config(**overrides):
    cfg_kwargs = dict(
        run_ai_detector=False, run_semantic=False, run_stylometric=False,
        run_self_plagiarism=False, run_watermark_detector=False,
        run_citation_network=False, run_coherence_analyzer=False,
        run_citation_check=False, run_venue_verification=False,
    )
    cfg_kwargs.update(overrides)
    return PipelineConfig(**cfg_kwargs)


class TestMathAndGrammarRunByDefault:

    def test_math_and_grammar_run_by_default(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT, encoding="utf-8")
        report = AEGISPipeline(config=_fast_config()).analyze(str(path))

        assert report.math_result is not None
        assert report.grammar_result is not None
        assert report.detector_status["math_check"]["status"] == "completed"
        assert report.detector_status["grammar_check"]["status"] == "completed"

    def test_can_be_disabled(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT, encoding="utf-8")
        cfg = _fast_config(run_math_check=False, run_grammar_check=False)
        report = AEGISPipeline(config=cfg).analyze(str(path))

        assert report.math_result is None
        assert report.grammar_result is None
        assert report.detector_status["math_check"]["status"] == "disabled"
        assert report.detector_status["grammar_check"]["status"] == "disabled"


class TestGuidelineComplianceOptIn:

    def test_disabled_by_default(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT, encoding="utf-8")
        report = AEGISPipeline(config=_fast_config()).analyze(str(path))

        assert report.guideline_results == {}
        assert report.detector_status["guideline_compliance"]["status"] == "disabled"

    def test_runs_each_requested_venue_separately(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT, encoding="utf-8")
        cfg = _fast_config(guideline_venues=("IEEE", "BCS", "ISACA"))
        report = AEGISPipeline(config=cfg).analyze(str(path))

        assert set(report.guideline_results.keys()) == {"IEEE", "BCS", "ISACA"}
        assert report.detector_status["guideline_compliance"]["status"] == "completed"


class TestComplianceSignalsDoNotAffectRisk:

    def test_grammar_and_math_issues_never_raise_overall_risk_above_low(self, tmp_path):
        # SAMPLE_TEXT has UK/US spelling mix, a contraction, a data/is
        # agreement issue, and a numbering gap ((1) then (3)) -- plenty of
        # math/grammar findings -- but no plagiarism/AI/citation signal,
        # so overall_risk must stay LOW.
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT, encoding="utf-8")
        report = AEGISPipeline(config=_fast_config()).analyze(str(path))

        assert report.math_result.all_issues, "expected the sample to trip a math issue"
        assert report.grammar_result.issues, "expected the sample to trip a grammar issue"
        assert report.overall_risk == "LOW"

    def test_math_and_grammar_medium_flags_surface_in_report_flags(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT, encoding="utf-8")
        report = AEGISPipeline(config=_fast_config()).analyze(str(path))

        assert any(f.startswith("[Math]") for f in report.flags)
