"""
Tests for the privacy/network-activity disclosure: the footer used to claim
"no data transmitted to third parties" unconditionally, even though citation
checking contacts Crossref (and citation-network analysis contacts OpenAlex)
by default. Reports must now say what was actually contacted for that run.
"""


from aegis.core.pipeline import AEGISPipeline, PipelineConfig
from aegis.report.generator import ReportGenerator


SAMPLE_TEXT_WITH_REFS = """
Introduction

This paper studies network security monitoring approaches for enterprise
DNS infrastructure and presents a novel anomaly detection pipeline.

References

[1] J. Smith, "A study of DNS anomalies," Journal of Security, 2021.
[2] A. Lee, "Deep learning for intrusion detection," IEEE Trans., 2022.
"""


class TestNetworkActivityTracking:

    def test_offline_citation_check_reports_no_services_contacted(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_WITH_REFS, encoding="utf-8")

        cfg = PipelineConfig(
            run_ai_detector=False, run_semantic=False, run_stylometric=False,
            run_self_plagiarism=False, run_watermark_detector=False,
            run_citation_network=False, run_coherence_analyzer=False,
            run_citation_check=True, citation_offline=True,
        )
        report = AEGISPipeline(config=cfg).analyze(str(path))

        assert report.network_activity["citation_check_mode"] == "offline"
        assert report.network_activity["external_services_contacted"] == []
        assert report.network_activity["document_content_transmitted"] is False

    def test_citation_check_disabled_reports_disabled_mode(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text(SAMPLE_TEXT_WITH_REFS, encoding="utf-8")

        cfg = PipelineConfig(
            run_ai_detector=False, run_semantic=False, run_stylometric=False,
            run_self_plagiarism=False, run_watermark_detector=False,
            run_citation_network=False, run_coherence_analyzer=False,
            run_citation_check=False,
        )
        report = AEGISPipeline(config=cfg).analyze(str(path))

        assert report.network_activity["citation_check_mode"] == "disabled"
        assert report.network_activity["external_services_contacted"] == []


class TestPrivacyDisclosureText:

    def _make_report_dict(self, network_activity):
        from aegis.core.pipeline import AnalysisReport
        from aegis.core.document import ParsedDocument
        doc = ParsedDocument(
            path="t.pdf", format="pdf", title=None, authors=[], abstract=None,
            full_text="text", sections=[], references=[],
        )
        report = AnalysisReport(
            submission_path="t.pdf", parsed_document=doc,
            overall_risk="LOW", flags=[], elapsed_seconds=1.0,
            network_activity=network_activity,
        )
        gen = ReportGenerator(".")
        return gen._report_to_dict(report), gen, report

    def test_no_services_contacted_message(self):
        d, gen, report = self._make_report_dict({
            "document_content_transmitted": False,
            "citation_check_mode": "offline",
            "citation_network_mode": "disabled",
            "external_services_contacted": [],
        })
        assert d["network_activity"]["external_services_contacted"] == []
        html = gen._render_html(d, report)
        assert "No external services were contacted" in html
        assert "no data transmitted to third parties" not in html.lower()

    def test_services_contacted_message_names_them(self):
        d, gen, report = self._make_report_dict({
            "document_content_transmitted": False,
            "citation_check_mode": "online",
            "citation_network_mode": "online",
            "external_services_contacted": ["Crossref", "OpenAlex"],
        })
        html = gen._render_html(d, report)
        assert "Crossref, OpenAlex" in html
        assert "never transmitted anywhere" in html

    def test_network_activity_included_in_json(self):
        d, gen, report = self._make_report_dict({
            "document_content_transmitted": False,
            "citation_check_mode": "online",
            "citation_network_mode": "disabled",
            "external_services_contacted": ["Crossref"],
        })
        assert d["network_activity"]["external_services_contacted"] == ["Crossref"]
