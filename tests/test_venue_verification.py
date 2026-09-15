"""
Tests for target-publisher verification (IEEE/ACM/Elsevier/IET/IETE/BCS).

No real Crossref calls: publisher_registry classification tests are pure
functions, and detector/pipeline tests patch out network-touching methods,
following the same pattern as test_citation_risk_scoring.py.
"""

from unittest.mock import patch

from aegis.core.pipeline import AEGISPipeline, PipelineConfig
from aegis.detectors.citation import CitationVerdict
from aegis.detectors.publisher_registry import (
    classify_publisher, claimed_publisher, resolve_target_publishers,
    DEFAULT_TARGET_PUBLISHERS,
)
from aegis.detectors.venue_verification import TargetPublisherVerifier


def _verdict(cite_key, doi, raw_text, resolved_journal, verdict="VALID"):
    return CitationVerdict(
        cite_key=cite_key, raw_text=raw_text, doi=doi,
        claimed_year="2023", claimed_authors=[], claimed_title="T",
        resolved_title="T", resolved_authors=[], resolved_year="2023",
        resolved_journal=resolved_journal, verdict=verdict, confidence=1.0,
        issues=[], crossref_url=None,
    )


class TestPublisherRegistryClassification:

    def test_ieee_prefix_classifies_without_container_title(self):
        assert classify_publisher("10.1109/TPAMI.2023.123", None) == "IEEE"

    def test_acm_prefix_classifies(self):
        assert classify_publisher("10.1145/3600000.3600001", None) == "ACM"

    def test_elsevier_prefix_classifies(self):
        assert classify_publisher("10.1016/j.eswa.2023.100000", None) == "Elsevier"

    def test_iet_prefix_classifies(self):
        assert classify_publisher("10.1049/iet-sen.2023.0001", None) == "IET"

    def test_unrelated_prefix_returns_none(self):
        assert classify_publisher("10.1000/unrelated.doi", None) is None

    def test_iete_requires_container_title_keyword(self):
        # 10.1080 is shared by thousands of unrelated Taylor & Francis
        # journals -- without a container-title hit it must NOT classify
        # as IETE just because the prefix matches.
        assert classify_publisher("10.1080/03772063.2023.1234567", None) is None
        assert classify_publisher(
            "10.1080/03772063.2023.1234567", "IETE Journal of Research"
        ) == "IETE"

    def test_bcs_requires_container_title_keyword(self):
        assert classify_publisher("10.1093/comjnl/bxad001", "Random OUP Journal") is None
        assert classify_publisher("10.1093/comjnl/bxad001", "The Computer Journal") == "BCS"

    def test_claimed_publisher_detects_ieee_keyword(self):
        assert claimed_publisher('X. Author, "A study," IEEE Trans. on Networking, 2023.') == "IEEE"

    def test_claimed_publisher_none_when_no_keyword(self):
        assert claimed_publisher('X. Author, "A study," Journal of Widgets, 2023.') is None

    def test_claimed_publisher_does_not_false_match_quiet(self):
        # "iet" is a substring of "quiet" -- a bare `in` check would
        # misclassify this as claiming IET even though it doesn't.
        assert claimed_publisher(
            'X. Author, "Design of a quiet cooling system," Journal of Widgets, 2023.'
        ) is None

    def test_claimed_publisher_does_not_false_match_quieted(self):
        # "iete" is a substring of "quieted" -- same collision for IETE.
        assert claimed_publisher(
            'The noise was quieted using active cancellation, Journal of Widgets, 2023.'
        ) is None

    def test_claimed_publisher_does_not_false_match_pacman(self):
        # "acm" is a substring of "pacman" -- same collision for ACM.
        assert claimed_publisher(
            'A study of pacman-style scheduling algorithms, Journal of Widgets, 2023.'
        ) is None

    def test_classify_publisher_does_not_false_match_quiet_container(self):
        assert classify_publisher(
            "10.1000/x.2023.1", "International Journal of Quiet Computing"
        ) is None

    def test_resolve_target_publishers_defaults_to_all_six(self):
        profiles = resolve_target_publishers(None)
        assert {p.key for p in profiles} == set(DEFAULT_TARGET_PUBLISHERS)

    def test_resolve_target_publishers_subset(self):
        profiles = resolve_target_publishers(["IEEE", "acm"])
        assert {p.key for p in profiles} == {"IEEE", "ACM"}


class TestTargetPublisherVerifierClaimChecks:

    def test_no_network_call_for_claim_check(self):
        """check_citation_claims must work purely off already-resolved
        CitationVerdict data -- no Crossref calls of its own."""
        verifier = TargetPublisherVerifier(offline=True)
        v = _verdict("r1", "10.1109/X.2023.1", "IEEE paper", "IEEE Trans. on X")
        counts, flags = verifier.check_citation_claims([v])
        assert counts["IEEE"] == 1
        assert flags == []

    def test_venue_mismatch_flagged_when_claim_does_not_match_resolved_doi(self):
        verifier = TargetPublisherVerifier(offline=True)
        v = _verdict(
            "r1", "10.1016/j.eswa.2023.1",
            'X. Author, "A study," IEEE Trans. on Networking, 2023.',
            "Expert Systems With Applications",  # actually Elsevier
        )
        counts, flags = verifier.check_citation_claims([v])
        assert counts["Elsevier"] == 1
        assert len(flags) == 1
        assert flags[0].flag_type == "VENUE_MISMATCH"
        assert flags[0].severity == "HIGH"
        assert flags[0].cite_key == "r1"

    def test_no_mismatch_when_reference_names_both_joint_sponsors(self):
        """Real bug: a jointly-sponsored venue is routinely named as both
        co-sponsors ("Proceedings of the IEEE/ACM 12th International
        Conference on ..."), and claimed_publisher() only ever returns the
        FIRST keyword match (IEEE, checked before ACM in TARGET_PUBLISHERS
        order) even when the DOI legitimately resolves to the other
        co-sponsor's Crossref member (ACM, DOI prefix 10.1145). That
        produced a false VENUE_MISMATCH ("reads as IEEE, but resolves to
        ACM") against a reference whose own text already said "IEEE/ACM"
        and whose DOI-resolved container-title also says "IEEE/ACM" --
        no misattribution occurred at all."""
        verifier = TargetPublisherVerifier(offline=True)
        v = _verdict(
            "r1", "10.1145/3773276.3776564",
            'J. Zouari, "Toward Agentic IAM," in Proceedings of the '
            "IEEE/ACM 12th International Conference on Big Data Computing, "
            "Applications and Technologies (BDCAT '25), 2025.",
            "Proceedings of the IEEE/ACM 12th International Conference on "
            "Big Data Computing, Applications and Technologies",  # ACM member
        )
        counts, flags = verifier.check_citation_claims([v])
        assert counts["ACM"] == 1
        assert flags == []

    def test_hallucinated_verdicts_excluded_from_classification(self):
        verifier = TargetPublisherVerifier(offline=True)
        v = CitationVerdict(
            cite_key="r1", raw_text="IEEE paper", doi="10.1/fake",
            claimed_year="2023", claimed_authors=[], claimed_title="T",
            resolved_title=None, resolved_authors=[], resolved_year=None,
            resolved_journal=None, verdict="HALLUCINATED", confidence=0.95,
            issues=["not found"], crossref_url=None,
        )
        counts, flags = verifier.check_citation_claims([v])
        assert counts["IEEE"] == 0
        assert flags == []

    def test_offline_search_returns_no_matches_without_network(self):
        verifier = TargetPublisherVerifier(offline=True)
        assert verifier.search_prior_publication("Some Paper Title") == []

    def test_search_skipped_without_title(self):
        verifier = TargetPublisherVerifier(offline=False)
        assert verifier.search_prior_publication("") == []


class TestPipelineWiring:

    def _fast_config(self, **overrides):
        cfg_kwargs = dict(
            run_ai_detector=False, run_semantic=False, run_stylometric=False,
            run_self_plagiarism=False, run_watermark_detector=False,
            run_citation_network=False, run_coherence_analyzer=False,
            run_citation_check=True, citation_offline=True,
            run_venue_verification=True, venue_offline=True,
        )
        cfg_kwargs.update(overrides)
        return PipelineConfig(**cfg_kwargs)

    def test_venue_verification_runs_by_default(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text("Introduction\n\nSome text.\n\nReferences\n", encoding="utf-8")
        pipeline = AEGISPipeline(config=self._fast_config())

        with patch.object(pipeline._citation, "verify_references", return_value=[]):
            report = pipeline.analyze(str(path))

        assert report.venue_verification_result is not None
        assert report.detector_status["venue_verification"]["status"] == "completed"

    def test_disabling_venue_check_skips_it(self, tmp_path):
        path = tmp_path / "paper.txt"
        path.write_text("Introduction\n\nSome text.\n\nReferences\n", encoding="utf-8")
        pipeline = AEGISPipeline(config=self._fast_config(run_venue_verification=False))

        with patch.object(pipeline._citation, "verify_references", return_value=[]):
            report = pipeline.analyze(str(path))

        assert report.venue_verification_result is None
        assert report.detector_status["venue_verification"]["status"] == "disabled"

    def test_venue_mismatch_flag_surfaces_in_report_flags(self, tmp_path):
        # Needs at least one parseable reference so the citation-check
        # branch in AEGISPipeline.analyze() actually calls the (patched)
        # verify_references -- an empty References section is skipped
        # before the mock is ever invoked.
        path = tmp_path / "paper.txt"
        path.write_text(
            "Introduction\n\nSome text.\n\n"
            'References\n\n[1] X. Author, "A study," IEEE Trans. on Networking, 2023.\n',
            encoding="utf-8",
        )
        pipeline = AEGISPipeline(config=self._fast_config())

        verdicts = [_verdict(
            "r1", "10.1016/j.eswa.2023.1",
            'X. Author, "A study," IEEE Trans. on Networking, 2023.',
            "Expert Systems With Applications",
        )]
        with patch.object(pipeline._citation, "verify_references", return_value=verdicts):
            report = pipeline.analyze(str(path))

        assert any("VENUE_MISMATCH" in f for f in report.flags)
        assert report.venue_verification_result.overall_risk == "HIGH"
