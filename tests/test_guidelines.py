"""Tests for per-venue guideline compliance checking."""

from aegis.detectors.math_formula import MathFormulaChecker
from aegis.detectors.grammar import GrammarLanguageChecker
from aegis.guidelines.checker import GuidelineComplianceChecker
from aegis.guidelines.profiles import (
    DEFAULT_GUIDELINE_VENUES, GUIDELINE_PROFILES, resolve_guideline_profiles,
)

_GRAMMAR = GrammarLanguageChecker(use_spacy=False)
_MATH = MathFormulaChecker()


def _run_check(text: str, venues=None):
    grammar_result = _GRAMMAR.analyze(text)
    math_result = _MATH.analyze("paper.pdf", "pdf", text)
    checker = GuidelineComplianceChecker(
        math_result=math_result, grammar_result=grammar_result,
        full_text=text, word_count=len(text.split()),
    )
    return checker.check_all(venues)


class TestProfileRegistry:

    def test_all_six_venues_present(self):
        assert set(GUIDELINE_PROFILES.keys()) == {
            "IEEE", "ACM", "BCS", "IET", "ISACA", "ELSEVIER",
        }

    def test_default_venues_matches_registry(self):
        assert set(DEFAULT_GUIDELINE_VENUES) == set(GUIDELINE_PROFILES.keys())

    def test_resolve_defaults_to_all_six(self):
        profiles = resolve_guideline_profiles(None)
        assert {p.key for p in profiles} == set(DEFAULT_GUIDELINE_VENUES)

    def test_resolve_subset_case_insensitive(self):
        profiles = resolve_guideline_profiles(["ieee", "Isaca"])
        assert {p.key for p in profiles} == {"IEEE", "ISACA"}


class TestScansRunSeparately:

    def test_each_requested_venue_gets_its_own_result(self):
        results = _run_check("A plain sentence with no notable issues here.",
                              ["IEEE", "ACM", "BCS", "IET", "ISACA", "ELSEVIER"])
        assert set(results.keys()) == {"IEEE", "ACM", "BCS", "IET", "ISACA", "ELSEVIER"}
        for venue, res in results.items():
            assert res.venue == venue
            assert res.source_name  # every venue must cite its own source
            assert res.source_url.startswith("http")

    def test_venue_specific_divergence_on_spelling(self):
        # UK spelling should read differently against IEEE/ACM/ISACA (US)
        # vs BCS/IET (UK) -- this is the core "checked separately" property.
        text = "We analyse the colour of the observed behaviour in detail."
        results = _run_check(text, ["IEEE", "BCS"])
        spelling_ieee = next(c for c in results["IEEE"].checks if "Spelling" in c.rule)
        spelling_bcs = next(c for c in results["BCS"].checks if "Spelling" in c.rule)
        assert spelling_ieee.status == "NEEDS_REVIEW"
        assert spelling_bcs.status == "PASS"


class TestContractionRule:

    def test_ieee_flags_contractions_bcs_does_not(self):
        text = "It's clear that we don't need this additional step at all."
        results = _run_check(text, ["IEEE", "BCS"])
        contraction_ieee = next(c for c in results["IEEE"].checks if c.rule == "Contractions")
        contraction_bcs = next(c for c in results["BCS"].checks if c.rule == "Contractions")
        assert contraction_ieee.status == "NEEDS_REVIEW"
        assert contraction_bcs.status == "PASS"


class TestIsacaSpecificRules:

    def test_first_person_flagged_only_for_isaca(self):
        text = "I believe this approach works well for most practitioners."
        results = _run_check(text, ["IEEE", "ISACA"])
        person_ieee = next(c for c in results["IEEE"].checks if "person" in c.rule.lower())
        person_isaca = next(c for c in results["ISACA"].checks if "person" in c.rule.lower())
        assert person_ieee.status == "NOT_ENOUGH_DATA"
        assert person_isaca.status == "NEEDS_REVIEW"

    def test_word_count_only_checked_for_isaca(self):
        text = "Short draft." * 5
        results = _run_check(text, ["IEEE", "ISACA"])
        wc_ieee = next(c for c in results["IEEE"].checks if "word count" in c.rule.lower())
        wc_isaca = next(c for c in results["ISACA"].checks if "word count" in c.rule.lower())
        assert wc_ieee.status == "NOT_ENOUGH_DATA"
        assert wc_isaca.status == "NEEDS_REVIEW"


class TestElsevierSpecificRules:

    def test_either_spelling_variant_passes_us_and_uk(self):
        us_text = "We analyze the color of the observed behavior in detail."
        uk_text = "We analyse the colour of the observed behaviour in detail."
        for text in (us_text, uk_text):
            results = _run_check(text, ["ELSEVIER"])
            spelling = next(c for c in results["ELSEVIER"].checks if "Spelling" in c.rule)
            assert spelling.status == "PASS"

    def test_either_spelling_variant_flags_mixed(self):
        text = "We analyse the color of the observed behaviour in detail."
        results = _run_check(text, ["IEEE", "ELSEVIER"])
        spelling_ieee = next(c for c in results["IEEE"].checks if "Spelling" in c.rule)
        spelling_elsevier = next(c for c in results["ELSEVIER"].checks if "Spelling" in c.rule)
        assert spelling_ieee.status == "NEEDS_REVIEW"
        assert spelling_elsevier.status == "NEEDS_REVIEW"

    def test_credit_statement_required_only_for_elsevier(self):
        text = "This paper has no author-contribution section at all."
        results = _run_check(text, ["IEEE", "ELSEVIER"])
        credit_ieee = next(c for c in results["IEEE"].checks if "CRediT" in c.rule)
        credit_elsevier = next(c for c in results["ELSEVIER"].checks if "CRediT" in c.rule)
        assert credit_ieee.status == "NOT_ENOUGH_DATA"
        assert credit_elsevier.status == "NEEDS_REVIEW"

    def test_credit_statement_detected_when_present(self):
        text = ("Some body text.\n\n"
                "CRediT authorship contribution statement\n"
                "Jane Doe: Conceptualization, Writing - Original Draft.")
        results = _run_check(text, ["ELSEVIER"])
        credit = next(c for c in results["ELSEVIER"].checks if "CRediT" in c.rule)
        assert credit.status == "PASS"

    def test_conflict_of_interest_and_data_availability_missing(self):
        text = "A short manuscript with none of the required Elsevier sections."
        results = _run_check(text, ["ELSEVIER"])
        coi = next(c for c in results["ELSEVIER"].checks
                    if "Competing Interest" in c.rule)
        data = next(c for c in results["ELSEVIER"].checks
                    if "Data Availability" in c.rule)
        assert coi.status == "NEEDS_REVIEW"
        assert data.status == "NEEDS_REVIEW"

    def test_conflict_of_interest_and_data_availability_present(self):
        text = ("Declaration of competing interest\n"
                "The authors declare no competing financial interests.\n\n"
                "Data availability\n"
                "Data will be made available on request.")
        results = _run_check(text, ["ELSEVIER"])
        coi = next(c for c in results["ELSEVIER"].checks
                    if "Competing Interest" in c.rule)
        data = next(c for c in results["ELSEVIER"].checks
                    if "Data Availability" in c.rule)
        assert coi.status == "PASS"
        assert data.status == "PASS"

    def test_highlights_within_limits_passes(self):
        text = ("Highlights\n"
                "- A novel L1L2R2 regularisation method is proposed.\n"
                "- Ensemble hyperparameter tuning improves accuracy notably.\n"
                "- The model outperforms prior state-of-the-art baselines.\n\n"
                "1. Introduction\nBody text follows here.")
        results = _run_check(text, ["ELSEVIER"])
        highlights = next(c for c in results["ELSEVIER"].checks if "Highlights" in c.rule)
        assert highlights.status == "PASS"

    def test_highlights_too_few_bullets_needs_review(self):
        text = ("Highlights\n"
                "- Only one bullet point here.\n\n"
                "1. Introduction\nBody text follows here.")
        results = _run_check(text, ["ELSEVIER"])
        highlights = next(c for c in results["ELSEVIER"].checks if "Highlights" in c.rule)
        assert highlights.status == "NEEDS_REVIEW"

    def test_highlights_not_required_for_other_venues(self):
        text = "Highlights\n- One bullet.\n\n1. Introduction\nBody text follows here."
        results = _run_check(text, ["IEEE"])
        highlights = next(c for c in results["IEEE"].checks if "Highlights" in c.rule)
        assert highlights.status == "NOT_ENOUGH_DATA"


class TestOverallStatus:

    def test_overall_needs_review_when_any_check_needs_review(self):
        text = "It's a bad example, don't you think?"
        results = _run_check(text, ["IEEE"])
        assert results["IEEE"].overall_status == "NEEDS_REVIEW"

    def test_never_reports_fail(self):
        # These are advisory style checks, never adjudicated pass/fail --
        # overall_status must only ever be one of these three values.
        text = "It's a bad example, don't you think? I really do."
        results = _run_check(text, list(DEFAULT_GUIDELINE_VENUES))
        assert "ELSEVIER" in results
        for res in results.values():
            assert res.overall_status in ("COMPLIANT", "NEEDS_REVIEW", "NOT_ENOUGH_DATA")
            for check in res.checks:
                assert check.status in ("PASS", "NEEDS_REVIEW", "NOT_ENOUGH_DATA")
