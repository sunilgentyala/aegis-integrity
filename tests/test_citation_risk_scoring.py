"""
Regression test for the real-world "CADLP" bug: a paper with a single
detected reference that was (incorrectly, pre-fix) reported as HALLUCINATED
received an overall CRITICAL risk verdict. Even independent of whether any
individual citation verdict is right or wrong, a sample of one reference
should never be enough on its own to force CRITICAL.
"""

from unittest.mock import patch

from aegis.core.pipeline import AEGISPipeline, PipelineConfig
from aegis.detectors.citation import CitationVerdict

SAMPLE_TEXT_ONE_REF = """
Introduction

This paper studies network security monitoring approaches for enterprise
DNS infrastructure and presents a novel anomaly detection pipeline that
operates entirely within the enterprise perimeter without external calls.

References

[1] Anonymous, "A study of DNS anomalies," Journal of Security, 2021.
"""

SAMPLE_TEXT_SIX_REFS = """
Introduction

This paper studies network security monitoring approaches for enterprise
DNS infrastructure and presents a novel anomaly detection pipeline.

References

[1] A. One, "Paper one," J. One, 2021.
[2] B. Two, "Paper two," J. Two, 2021.
[3] C. Three, "Paper three," J. Three, 2021.
[4] D. Four, "Paper four," J. Four, 2021.
[5] E. Five, "Paper five," J. Five, 2021.
[6] F. Six, "Paper six," J. Six, 2021.
"""


def _fast_config(**overrides):
    cfg_kwargs = dict(
        run_ai_detector=False, run_semantic=False, run_stylometric=False,
        run_self_plagiarism=False, run_watermark_detector=False,
        run_citation_network=False, run_coherence_analyzer=False,
        run_citation_check=True, citation_offline=True,
    )
    cfg_kwargs.update(overrides)
    return PipelineConfig(**cfg_kwargs)


def _hallucinated_verdict(key):
    return CitationVerdict(
        cite_key=key, raw_text="", doi=f"10.1/{key}",
        claimed_year="2021", claimed_authors=[], claimed_title="Fake",
        resolved_title=None, resolved_authors=[], resolved_year=None,
        resolved_journal=None, verdict="HALLUCINATED", confidence=0.95,
        issues=["DOI not found"], crossref_url=None,
    )


def _valid_verdict(key):
    return CitationVerdict(
        cite_key=key, raw_text="", doi=f"10.1/{key}",
        claimed_year="2021", claimed_authors=[], claimed_title="T",
        resolved_title="T", resolved_authors=[], resolved_year="2021",
        resolved_journal="J", verdict="VALID", confidence=1.0,
        issues=[], crossref_url=None,
    )


class TestCitationRiskScoringSampleSizeGate:

    def test_single_false_hallucination_does_not_force_critical(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_ONE_REF, encoding="utf-8")
        pipeline = AEGISPipeline(config=_fast_config())

        with patch.object(pipeline._citation, "verify_references",
                           return_value=[_hallucinated_verdict("ref_0")]):
            report = pipeline.analyze(str(path))

        assert report.overall_risk != "CRITICAL", (
            "A single reference's verdict should never be enough sample "
            "size to force CRITICAL risk on its own"
        )
        assert report.citation_summary["assessment"] == "INCONCLUSIVE"
        assert any("INCONCLUSIVE" in f for f in report.flags)

    def test_six_hallucinated_out_of_six_is_critical(self, tmp_path):
        """With an adequate sample, genuine hallucinations must still be
        able to drive risk to CRITICAL -- the gate is about sample size,
        not about suppressing real findings."""
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_SIX_REFS, encoding="utf-8")
        pipeline = AEGISPipeline(config=_fast_config())

        verdicts = [_hallucinated_verdict(f"ref_{i}") for i in range(6)]
        with patch.object(pipeline._citation, "verify_references", return_value=verdicts):
            report = pipeline.analyze(str(path))

        assert report.overall_risk == "CRITICAL"
        assert report.citation_summary["assessment"] == "ASSESSED"

    def test_six_valid_references_is_not_flagged_inconclusive(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_SIX_REFS, encoding="utf-8")
        pipeline = AEGISPipeline(config=_fast_config())

        verdicts = [_valid_verdict(f"ref_{i}") for i in range(6)]
        with patch.object(pipeline._citation, "verify_references", return_value=verdicts):
            report = pipeline.analyze(str(path))

        assert report.citation_summary["assessment"] == "ASSESSED"
        assert not any("INCONCLUSIVE" in f for f in report.flags)

    def test_unresolvable_verdicts_do_not_inflate_citation_score(self, tmp_path):
        """UNRESOLVABLE means 'network/parse failure', not a confirmed
        integrity problem -- it must not count toward citation_score."""
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_SIX_REFS, encoding="utf-8")
        pipeline = AEGISPipeline(config=_fast_config())

        unresolvable = CitationVerdict(
            cite_key="u", raw_text="", doi="10.1/u",
            claimed_year=None, claimed_authors=[], claimed_title=None,
            resolved_title=None, resolved_authors=[], resolved_year=None,
            resolved_journal=None, verdict="UNRESOLVABLE", confidence=0.0,
            issues=["network error"], crossref_url=None,
        )
        verdicts = [unresolvable] + [_valid_verdict(f"ref_{i}") for i in range(5)]
        with patch.object(pipeline._citation, "verify_references", return_value=verdicts):
            report = pipeline.analyze(str(path))

        assert report.citation_score == 0.0
