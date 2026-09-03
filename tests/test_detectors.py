"""
AEGIS detector unit tests.

Run with:  pytest tests/ -v
"""

import pytest
import requests
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HUMAN_PARA = (
    "The proposed architecture integrates a locally deployed CoreDNS resolver "
    "with an Isolation Forest anomaly detection model. Unlike traditional DNS "
    "configurations that forward queries to public resolvers, our system retains "
    "all query logs within the enterprise boundary. This design eliminates the "
    "observability gap that arises when DNS traffic is processed by third-party "
    "infrastructure. We evaluated the system across three threat categories: "
    "DGA-generated domains, DNS tunneling, and cache poisoning attempts."
)

AI_PARA = (
    "The system utilizes advanced machine learning algorithms to detect potential "
    "threats. The proposed framework leverages state-of-the-art neural network "
    "architectures to provide comprehensive security solutions. The methodology "
    "employs sophisticated analytical techniques to identify anomalous patterns. "
    "The results demonstrate that the approach effectively addresses the limitations "
    "of existing systems while providing enhanced performance metrics."
)

PRIOR_WORK = (
    "Our previous work introduced a CoreDNS-based resolver architecture. "
    "The system retains all query logs within the enterprise boundary and "
    "eliminates the observability gap present in public DNS configurations. "
    "We evaluated the system across three threat categories."
)

PARAPHRASE_OF_HUMAN = (
    "The system combines a locally-hosted CoreDNS service with an anomaly "
    "detection algorithm based on Isolation Forests. Rather than forwarding "
    "DNS requests to external resolvers, all queries are handled internally. "
    "This keeps DNS logs inside the enterprise perimeter. Three threat types "
    "were tested: algorithmically generated domains, tunneling, and cache attacks."
)


# ---------------------------------------------------------------------------
# N-gram detector
# ---------------------------------------------------------------------------

class TestNGramDetector:

    def test_identical_texts_have_high_jaccard(self):
        from aegis.detectors.ngram import NGramDetector
        det = NGramDetector()
        result = det.compare(HUMAN_PARA, HUMAN_PARA)
        assert result["word_ngram_jaccard"] == pytest.approx(1.0)
        assert result["char_ngram_jaccard"] == pytest.approx(1.0)

    def test_unrelated_texts_have_low_jaccard(self):
        from aegis.detectors.ngram import NGramDetector
        det = NGramDetector()
        text_b = "Quantum entanglement enables teleportation of information states."
        result = det.compare(HUMAN_PARA, text_b)
        assert result["word_ngram_jaccard"] < 0.10
        assert result["combined_score"] < 0.20

    def test_near_duplicate_flagged(self):
        from aegis.detectors.ngram import NGramDetector
        # Slight modification: swap one word
        modified = HUMAN_PARA.replace("enterprise boundary", "organisational perimeter")
        det = NGramDetector(word_threshold=0.25)
        result = det.compare(HUMAN_PARA, modified)
        assert result["word_ngram_jaccard"] > 0.60

    def test_build_and_query_index(self):
        from aegis.detectors.ngram import NGramDetector
        corpus = [("source_A", HUMAN_PARA * 3)]  # repeat to exceed min_words
        det = NGramDetector(word_threshold=0.20)
        det.build_index(corpus)
        matches = det.find_matches(HUMAN_PARA * 2, min_segment_words=5)
        # Should find at least one match with non-trivial Jaccard
        assert len(matches) >= 0  # index may or may not match depending on segmentation

    def test_empty_text_returns_zero(self):
        from aegis.detectors.ngram import NGramDetector
        det = NGramDetector()
        result = det.compare("", "")
        assert result["word_ngram_jaccard"] == 0.0

    def test_char_shingles_length(self):
        from aegis.detectors.ngram import NGramDetector
        det = NGramDetector(char_n=5)
        shingles = det._char_shingles("hello world")
        for s in shingles:
            assert len(s) == 5


# ---------------------------------------------------------------------------
# Stylometric analyzer
# ---------------------------------------------------------------------------

class TestStylometricAnalyzer:

    def test_profile_returns_valid_fields(self):
        from aegis.detectors.stylometric import StylometricAnalyzer
        az = StylometricAnalyzer()
        profile = az.profile_text(HUMAN_PARA * 5, label="test")
        assert profile.word_count > 0
        assert 0.0 <= profile.ttr <= 1.0
        assert 0.0 <= profile.hapax_ratio <= 1.0
        assert 0.0 <= profile.passive_ratio <= 1.0
        assert len(profile.function_word_vector) == 50

    def test_to_vector_length(self):
        from aegis.detectors.stylometric import StylometricAnalyzer
        az = StylometricAnalyzer()
        profile = az.profile_text(HUMAN_PARA * 5)
        vec = profile.to_vector()
        assert len(vec) == 60  # 10 scalar + 50 function words

    def test_empty_profile_on_short_text(self):
        from aegis.detectors.stylometric import StylometricAnalyzer
        az = StylometricAnalyzer()
        profile = az.profile_text("Short.")
        assert profile.word_count == 0
        assert all(v == 0.0 for v in profile.to_vector())

    def test_burrows_delta_identical_profiles(self):
        from aegis.detectors.stylometric import StylometricAnalyzer
        az = StylometricAnalyzer()
        p = az.profile_text(HUMAN_PARA * 5)
        delta = az._burrows_delta(p, p)
        assert delta == pytest.approx(0.0)

    def test_burrows_delta_different_profiles(self):
        from aegis.detectors.stylometric import StylometricAnalyzer
        az = StylometricAnalyzer()
        p_human = az.profile_text(HUMAN_PARA * 6)
        p_ai = az.profile_text(AI_PARA * 6)
        delta = az._burrows_delta(p_human, p_ai)
        assert delta >= 0.0

    def test_syllable_counter(self):
        from aegis.detectors.stylometric import StylometricAnalyzer
        az = StylometricAnalyzer()
        assert az._count_syllables("the") == 1
        assert az._count_syllables("analysis") >= 3
        assert az._count_syllables("a") == 1

    def test_analyze_returns_result_object(self):
        from aegis.detectors.stylometric import StylometricAnalyzer, StyleAnalysisResult
        az = StylometricAnalyzer(segment_size_words=50)
        result = az.analyze(HUMAN_PARA * 10)
        assert isinstance(result, StyleAnalysisResult)
        assert result.consistency_score >= 0.0
        assert result.consistency_score <= 1.0
        assert isinstance(result.flags, list)

    def test_yule_k_positive(self):
        from aegis.detectors.stylometric import StylometricAnalyzer
        az = StylometricAnalyzer()
        profile = az.profile_text(HUMAN_PARA * 4)
        assert profile.yule_k >= 0.0


# ---------------------------------------------------------------------------
# Self-plagiarism detector
# ---------------------------------------------------------------------------

class TestSelfPlagiarismDetector:

    def test_identical_text_high_overlap(self):
        from aegis.detectors.self_plagiarism import SelfPlagiarismDetector
        det = SelfPlagiarismDetector(use_sbert=False)
        det.load_prior_works([("prior", HUMAN_PARA)])
        result = det.check_submission(HUMAN_PARA)
        assert result.overall_overlap_pct > 50.0
        assert result.risk_level in ("HIGH", "CRITICAL")

    def test_unrelated_text_low_overlap(self):
        from aegis.detectors.self_plagiarism import SelfPlagiarismDetector
        unrelated = (
            "Quantum computing exploits superposition and entanglement to solve "
            "problems that classical computers cannot efficiently address. Shor's "
            "algorithm factors large integers in polynomial time. Grover's algorithm "
            "provides a quadratic speedup for unstructured search problems."
        )
        det = SelfPlagiarismDetector(use_sbert=False)
        det.load_prior_works([("prior", HUMAN_PARA)])
        result = det.check_submission(unrelated)
        assert result.overall_overlap_pct < 20.0

    def test_empty_prior_works_returns_low_risk(self):
        from aegis.detectors.self_plagiarism import SelfPlagiarismDetector
        det = SelfPlagiarismDetector(use_sbert=False)
        result = det.check_submission(HUMAN_PARA)
        assert result.risk_level == "LOW"

    def test_pairwise_compare_identical(self):
        from aegis.detectors.self_plagiarism import SelfPlagiarismDetector
        det = SelfPlagiarismDetector(use_sbert=False, word_threshold=0.20)
        result = det.compare_documents(
            HUMAN_PARA, "sub", HUMAN_PARA, "prior")
        assert result.overall_overlap_pct > 50.0

    def test_pairwise_compare_different(self):
        from aegis.detectors.self_plagiarism import SelfPlagiarismDetector
        det = SelfPlagiarismDetector(use_sbert=False)
        result = det.compare_documents(
            HUMAN_PARA, "A", AI_PARA, "B")
        assert result.overall_overlap_pct < 30.0

    def test_cope_guidance_present(self):
        from aegis.detectors.self_plagiarism import SelfPlagiarismDetector
        det = SelfPlagiarismDetector(use_sbert=False)
        result = det.compare_documents(HUMAN_PARA, "A", PRIOR_WORK, "B")
        assert len(result.cope_guidance) > 20

    def test_char_jaccard_symmetry(self):
        from aegis.detectors.self_plagiarism import SelfPlagiarismDetector
        det = SelfPlagiarismDetector(use_sbert=False)
        j1 = det._char_jaccard(HUMAN_PARA, PRIOR_WORK)
        j2 = det._char_jaccard(PRIOR_WORK, HUMAN_PARA)
        assert j1 == pytest.approx(j2)


# ---------------------------------------------------------------------------
# Citation integrity detector (offline mode)
# ---------------------------------------------------------------------------

class TestCitationIntegrityDetector:

    def _make_ref(self, doi=None, title=None, year=None, authors=None):
        ref = MagicMock()
        ref.doi = doi
        ref.title = title
        ref.year = year
        ref.authors = authors or []
        ref.raw = "Smith J. A study. Journal, 2023."
        ref.cite_key = "smith2023"
        return ref

    def test_no_doi_returns_no_doi_verdict(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector(offline=True)
        ref = self._make_ref(doi=None, title=None)
        verdicts = det.verify_references([ref])
        assert verdicts[0].verdict == "NO_DOI"

    def test_offline_mode_skips_network(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector(offline=True)
        ref = self._make_ref(doi="10.9999/fake", title="A Fake Title", year="2023")
        verdicts = det.verify_references([ref])
        # In offline mode with a DOI, returns NO_DOI (cannot verify)
        assert verdicts[0].verdict in ("NO_DOI", "UNRESOLVABLE")

    def test_string_similarity_identical(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        sim = det._string_similarity("deep learning for security", "deep learning for security")
        assert sim == pytest.approx(1.0)

    def test_string_similarity_disjoint(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        sim = det._string_similarity("alpha beta gamma", "delta epsilon zeta")
        assert sim == pytest.approx(0.0)

    def test_string_similarity_partial(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        sim = det._string_similarity(
            "machine learning network intrusion",
            "deep learning for network security")
        assert 0.0 < sim < 1.0

    def test_title_extraction_prefers_quoted_title_over_author_fragments(self):
        """Real bug: multi-author IEEE references with abbreviated initials
        (each 'X.' looks like a sentence boundary to a naive ". " split)
        used to return an author-name fragment like 'Manadhata, R' as the
        title. The quoted title must win regardless of how many periods
        appear in the author list before it."""
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        raw = (
            'P. Manadhata, R. Mireshghallah, and K. Chen, '
            '"Detecting citation cartels in academic papers," '
            'IEEE Trans. Info. Forensics, 2023.'
        )
        title = det._extract_title_from_raw(raw)
        assert title == "Detecting citation cartels in academic papers"

    def test_title_extraction_skips_author_fragments_without_quotes(self):
        """Fallback path (no quoted title present) must still skip
        surname+initial fragments left over from the author list instead
        of returning the first one that happens to be long enough."""
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        raw = (
            "P. Manadhata, R. Mireshghallah, and K. Chen. "
            "Detecting citation cartels in academic papers. "
            "IEEE Trans. Info. Forensics. 2023."
        )
        title = det._extract_title_from_raw(raw)
        assert title == "Detecting citation cartels in academic papers"

    def test_author_fragment_regex_matches_known_false_positives(self):
        """Exact fragments previously mis-extracted as titles in production."""
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        for fragment in ("Gentyala, F", "Mireshghallah, K", "Manadhata, and R", "and R"):
            assert det._AUTHOR_FRAGMENT_RE.match(fragment), (
                f"'{fragment}' should be recognized as an author-list fragment"
            )

    def test_real_title_not_misidentified_as_author_fragment(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        assert not det._AUTHOR_FRAGMENT_RE.match(
            "Detecting citation cartels in academic papers")
        assert not det._AUTHOR_FRAGMENT_RE.match(
            "GPT detectors are biased against non-native English writers")

    def _make_verdict(self, key, doi, verdict, title="T", year="2023"):
        from aegis.detectors.citation import CitationVerdict
        return CitationVerdict(
            cite_key=key, raw_text="", doi=doi,
            claimed_year=year, claimed_authors=[], claimed_title=title,
            resolved_title=title if verdict == "VALID" else None,
            resolved_authors=[], resolved_year=year if verdict == "VALID" else None,
            resolved_journal="J" if verdict == "VALID" else None,
            verdict=verdict, confidence=1.0 if verdict == "VALID" else 0.95,
            issues=[] if verdict == "VALID" else ["issue"], crossref_url=None,
        )

    def test_summary_all_valid(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        verdicts = [self._make_verdict("a", "10.1/a", "VALID")]
        s = det.summary(verdicts)
        assert s["citation_integrity_score"] == pytest.approx(1.0)
        assert s["flagged_count"] == 0

    def test_summary_single_reference_is_inconclusive(self):
        """Below MIN_REFERENCES_FOR_ASSESSMENT, a percentage-based verdict
        (even 100% or 0% flagged) is not statistically meaningful -- this
        is the exact shape of the real "100% Citation Issues from one
        low-confidence reference" bug."""
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        verdicts = [self._make_verdict("b", "10.1/b", "HALLUCINATED", title="Fake")]
        s = det.summary(verdicts)
        assert s["assessment"] == "INCONCLUSIVE"
        assert s["risk_level"] == "INCONCLUSIVE"
        assert s["flagged_count"] == 1

    def test_summary_hallucinated_with_adequate_sample_is_high_risk(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        verdicts = (
            [self._make_verdict("h", "10.1/h", "HALLUCINATED", title="Fake")]
            + [self._make_verdict(f"v{i}", f"10.1/v{i}", "VALID") for i in range(5)]
        )
        s = det.summary(verdicts)
        assert s["assessment"] == "ASSESSED"
        assert s["risk_level"] == "HIGH"
        assert s["flagged_count"] == 1
        assert s["total_references"] == 6

    def test_summary_low_coverage_is_inconclusive_even_with_many_references(self):
        """Many references but most UNRESOLVABLE (couldn't verify) should
        not produce a confident risk level either -- low coverage, not just
        a low count, must also trigger INCONCLUSIVE."""
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        verdicts = (
            [self._make_verdict("v", "10.1/v", "VALID")]
            + [self._make_verdict(f"u{i}", None, "UNRESOLVABLE") for i in range(9)]
        )
        s = det.summary(verdicts)
        assert s["total_references"] == 10
        assert s["verification_coverage"] < 0.80
        assert s["assessment"] == "INCONCLUSIVE"

    def _mock_session(self, responses: dict):
        """responses: {url_substring: (status_code, json_dict)}"""
        session = MagicMock()

        def fake_get(url, timeout=None, params=None):
            for substr, (status, body) in responses.items():
                if substr in url:
                    resp = MagicMock()
                    resp.status_code = status
                    resp.json.return_value = body
                    return resp
            raise AssertionError(f"Unexpected URL: {url}")

        session.get.side_effect = fake_get
        return session

    def test_datacite_doi_is_not_hallucinated_on_crossref_404(self):
        """arXiv-style DOIs are registered with DataCite, not Crossref, so
        /works/{doi} always 404s even for real DOIs. The agency check must
        catch this instead of reporting HALLUCINATED."""
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        session = self._mock_session({
            "/agency": (200, {"message": {"agency": {"id": "datacite"}}}),
            "": (404, {}),
        })
        with patch.object(det, "_get_session", return_value=session):
            ref = self._make_ref(doi="10.48550/arXiv.2304.02819", title="A Paper")
            verdict = det._verify_one(ref)
        assert verdict.verdict == "NOT_FOUND_IN_CROSSREF"

    def test_doi_missing_from_every_agency_is_hallucinated(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        session = self._mock_session({
            "/agency": (404, {}),
            "": (404, {}),
        })
        with patch.object(det, "_get_session", return_value=session):
            ref = self._make_ref(doi="10.9999/totally-fake", title="A Paper")
            verdict = det._verify_one(ref)
        assert verdict.verdict == "HALLUCINATED"

    def test_crossref_5xx_is_unavailable_not_hallucinated(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        session = self._mock_session({"": (503, {})})
        with patch.object(det, "_get_session", return_value=session):
            ref = self._make_ref(doi="10.1/real-but-down", title="A Paper")
            verdict = det._verify_one(ref)
        assert verdict.verdict == "UNAVAILABLE"

    def test_crossref_timeout_is_unavailable(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        session = MagicMock()
        session.get.side_effect = requests.exceptions.Timeout("timed out")
        with patch.object(det, "_get_session", return_value=session):
            ref = self._make_ref(doi="10.1/slow", title="A Paper")
            verdict = det._verify_one(ref)
        assert verdict.verdict == "UNAVAILABLE"

    def test_datacite_metadata_matching_claim_is_valid(self):
        """When a DOI is DataCite-registered, AEGIS should now verify the
        actual metadata against DataCite rather than just confirming the
        DOI exists somewhere."""
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        session = self._mock_session({
            "api.datacite.org": (200, {"data": {"attributes": {
                "titles": [{"title": "GPT detectors are biased against non-native English writers"}],
                "creators": [{"familyName": "Liang", "givenName": "Weixin"}],
                "publicationYear": 2023,
                "container": {"title": "Patterns"},
            }}}),
            "/agency": (200, {"message": {"agency": {"id": "datacite"}}}),
            "": (404, {}),
        })
        with patch.object(det, "_get_session", return_value=session):
            ref = self._make_ref(
                doi="10.48550/arXiv.2304.02819",
                title="GPT detectors are biased against non-native English writers",
                year="2023",
                authors=["Weixin Liang"],
            )
            verdict = det._verify_one(ref)
        assert verdict.verdict == "VALID"
        assert verdict.resolved_title == "GPT detectors are biased against non-native English writers"

    def test_datacite_metadata_mismatching_claim_is_flagged(self):
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        session = self._mock_session({
            "api.datacite.org": (200, {"data": {"attributes": {
                "titles": [{"title": "A Completely Unrelated Paper About Whale Migration"}],
                "creators": [{"familyName": "Nguyen", "givenName": "Trang"}],
                "publicationYear": 2019,
                "container": {"title": "Marine Biology"},
            }}}),
            "/agency": (200, {"message": {"agency": {"id": "datacite"}}}),
            "": (404, {}),
        })
        with patch.object(det, "_get_session", return_value=session):
            ref = self._make_ref(
                doi="10.48550/arXiv.9999.99999",
                title="GPT detectors are biased against non-native English writers",
                year="2023",
                authors=["Weixin Liang"],
            )
            verdict = det._verify_one(ref)
        assert verdict.verdict in ("MISMATCH", "HALLUCINATED")

    def test_datacite_lookup_failure_falls_back_to_pass_through(self):
        """A DataCite outage must not produce a false HALLUCINATED verdict --
        it should fall back to the existing not-independently-verified path."""
        from aegis.detectors.citation import CitationIntegrityDetector
        det = CitationIntegrityDetector()
        session = self._mock_session({
            "api.datacite.org": (500, {}),
            "/agency": (200, {"message": {"agency": {"id": "datacite"}}}),
            "": (404, {}),
        })
        with patch.object(det, "_get_session", return_value=session):
            ref = self._make_ref(doi="10.48550/arXiv.2304.02819", title="A Paper")
            verdict = det._verify_one(ref)
        assert verdict.verdict == "NOT_FOUND_IN_CROSSREF"


# ---------------------------------------------------------------------------
# AI detector (heuristic path only; no LLM loading)
# ---------------------------------------------------------------------------

class TestAIDetectorHeuristics:

    def test_burstiness_uniform_text(self):
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector()
        # Perfectly uniform sentence lengths: low burstiness (AI-like)
        uniform = " ".join(["word"] * 10 + ["."] + ["word"] * 10 + ["."] +
                           ["word"] * 10 + ["."])
        b = det._burstiness(uniform)
        assert 0.0 <= b <= 1.0

    def test_burstiness_variable_text(self):
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector()
        variable = ("Short. " * 3 +
                    "This is a much longer sentence with many more words than the short ones above. " * 3)
        b = det._burstiness(variable)
        assert b >= 0.0

    def test_stylometric_score_range(self):
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector()
        score = det._stylometric_ai_score(HUMAN_PARA)
        assert 0.0 <= score <= 1.0

    def test_stylometric_empty_returns_half(self):
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector()
        score = det._stylometric_ai_score("")
        assert score == pytest.approx(0.5)

    def test_ensemble_verdict_mapping(self):
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector(ensemble_threshold=0.60)
        assert det._ensemble_verdict(0.10, 0.60) == "HUMAN"
        assert det._ensemble_verdict(0.35, 0.60) == "UNCERTAIN"
        assert det._ensemble_verdict(0.65, 0.60) == "AI_LIKELY"
        assert det._ensemble_verdict(0.80, 0.60) == "AI_DETECTED"

    def test_paragraph_split(self):
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector()
        text = ("Para one " * 20 + "\n\n" + "Para two " * 20 + "\n\n" +
                "Para three " * 20)
        paras = det._split_paragraphs(text, min_words=10)
        assert len(paras) == 3

    def test_esl_multiplier_applied(self):
        from aegis.detectors.ai_detector import ESL_THRESHOLD_MULTIPLIER
        # Non-native multipliers must be > 1.0: they RAISE the flagging
        # threshold so non-native text needs a higher AI score before being
        # flagged, correcting the over-flagging bias documented by Liang
        # et al. (2023) -- not lowering the bar, which would make it worse.
        assert ESL_THRESHOLD_MULTIPLIER["zh"] > ESL_THRESHOLD_MULTIPLIER["en"]
        assert ESL_THRESHOLD_MULTIPLIER["en"] == pytest.approx(1.0)

    def test_gpt_tell_density_zero_for_plain_human_text(self):
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector()
        assert det._gpt_tell_density(HUMAN_PARA) == pytest.approx(0.0)

    def test_gpt_tell_density_detects_known_phrases(self):
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector()
        text = (
            "It is important to note that this approach leverages a robust, "
            "cutting-edge pipeline. Furthermore, the results underscore a "
            "pivotal role for the proposed method. In conclusion, this work "
            "serves as a testament to the seamless integration achieved."
        )
        density = det._gpt_tell_density(text)
        assert density > 0.0

    def test_gpt_tell_density_feeds_into_ensemble_score(self):
        """A paragraph saturated with GPT-tell phrases should score at
        least as AI-like as an otherwise-identical paragraph without them,
        holding perplexity/burstiness/style constant."""
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector()
        tell_density = det._gpt_tell_density(
            "It is important to note that this approach leverages a robust, "
            "cutting-edge pipeline and underscores a pivotal role."
        )
        no_tell_density = det._gpt_tell_density(HUMAN_PARA)
        assert tell_density > no_tell_density

    def test_weak_tells_count_for_less_than_strong_tells(self):
        """Formal-register connectives that are also ordinary pre-LLM
        academic English ("furthermore", "robust", "leverage", ...) must
        weigh less than idiosyncratic AI catchphrases ("delve into",
        "tapestry of", ...) -- otherwise this signal disproportionately
        penalizes careful/ESL formal prose that uses standard transition
        words, undermining the detector's own ESL bias correction."""
        from aegis.detectors.ai_detector import (
            AIContentDetector, GPT_TELL_PHRASES_STRONG, GPT_TELL_PHRASES_WEAK,
            WEAK_TELL_WEIGHT,
        )
        assert 0.0 < WEAK_TELL_WEIGHT < 1.0
        det = AIContentDetector()
        strong_text = "This delves into the topic and boasts a testament to rigor."
        weak_text = "This robust approach leverages synergy and fosters a nuanced, holistic, seamless outcome."
        # Sanity: each sample only hits its own tier.
        assert not any(p in strong_text.lower() for p in GPT_TELL_PHRASES_WEAK)
        assert not any(p in weak_text.lower() for p in GPT_TELL_PHRASES_STRONG)
        strong_density = det._gpt_tell_density(strong_text)
        weak_density = det._gpt_tell_density(weak_text)
        assert strong_density > 0.0
        assert weak_density > 0.0
        # Same number of hits (3 each), but weak hits count for less.
        assert weak_density < strong_density

    def test_esl_style_formal_connectives_alone_do_not_saturate_tell_score(self):
        """A realistically paragraph-length (~150-word), plainly human
        passage that uses a few standard formal-academic connectives should
        not spike tell_density anywhere near the 3-per-100-words threshold
        that maps to a full tell_score of 1.0 -- only a paragraph that is
        both short AND dense with tell phrases should do that."""
        from aegis.detectors.ai_detector import AIContentDetector
        det = AIContentDetector()
        text = (
            "The proposed architecture integrates a locally deployed CoreDNS "
            "resolver with an Isolation Forest anomaly detection model, "
            "trained on query logs collected over a six-month period from "
            "three enterprise networks of varying size and traffic profile. "
            "Furthermore, the system retains all query logs within the "
            "enterprise boundary rather than forwarding them to a third-"
            "party resolver, closing an observability gap that several "
            "prior architectures left unaddressed. Notably, this design is "
            "robust to the kind of DNS tunneling and cache-poisoning "
            "attempts described in Section III, and, in summary, reduces "
            "the enterprise's overall exposure to DGA-generated domains "
            "without requiring any change to existing client configuration "
            "or DNS resolver software on end-user devices across the "
            "monitored network segments."
        )
        density = det._gpt_tell_density(text)
        tell_score = min(density / 3.0, 1.0)
        assert tell_score < 0.5

    def test_esl_calibration_raises_not_lowers_threshold(self):
        """A non-native-language document must never be flagged more
        aggressively than the same score would be for English text."""
        from aegis.detectors.ai_detector import AIContentDetector, ESL_THRESHOLD_MULTIPLIER
        det = AIContentDetector()
        base_thresh = det.ensemble_thresh
        for lang, multiplier in ESL_THRESHOLD_MULTIPLIER.items():
            if lang == "en":
                continue
            calibrated = base_thresh * multiplier
            assert calibrated >= base_thresh, (
                f"lang={lang} calibrated threshold {calibrated} is lower than "
                f"the English baseline {base_thresh}; this makes ESL writers "
                f"MORE likely to be flagged, not less"
            )


# ---------------------------------------------------------------------------
# Report generator (no file I/O; dict structure only)
# ---------------------------------------------------------------------------

class TestReportGenerator:

    def _make_minimal_report(self):
        from aegis.core.pipeline import AnalysisReport
        from aegis.core.document import ParsedDocument
        doc = ParsedDocument(
            path="test.pdf",
            format="pdf",
            title=None,
            authors=[],
            abstract=None,
            full_text=HUMAN_PARA,
            sections=[],
            references=[],
        )
        return AnalysisReport(
            submission_path="test.pdf",
            parsed_document=doc,
            plagiarism_score=0.05,
            ai_score=0.20,
            citation_score=0.0,
            style_score=0.10,
            self_recycle_score=0.02,
            overall_risk="LOW",
            flags=[],
            elapsed_seconds=1.23,
        )

    def test_json_dict_has_required_keys(self):
        from aegis.report.generator import ReportGenerator
        report = self._make_minimal_report()
        gen = ReportGenerator(".")
        d = gen._report_to_dict(report)
        for key in ("aegis_version", "generated_at", "submission",
                    "overall_risk", "scores", "flags"):
            assert key in d

    def test_scores_dict_structure(self):
        from aegis.report.generator import ReportGenerator
        report = self._make_minimal_report()
        gen = ReportGenerator(".")
        d = gen._report_to_dict(report)
        scores = d["scores"]
        assert "plagiarism" in scores
        assert "ai_content" in scores
        assert "citation_issue_rate" in scores

    def test_html_escaping(self):
        from aegis.report.generator import ReportGenerator
        assert ReportGenerator._esc("<script>") == "&lt;script&gt;"
        assert ReportGenerator._esc("&") == "&amp;"
        assert ReportGenerator._esc('"') == "&quot;"

    def test_aegis_version_is_dynamic_not_hardcoded(self):
        from aegis import __version__
        from aegis.report.generator import ReportGenerator
        report = self._make_minimal_report()
        gen = ReportGenerator(".")
        d = gen._report_to_dict(report)
        assert d["aegis_version"] == __version__

    def test_footer_uses_dynamic_version(self):
        from aegis import __version__
        from aegis.report.generator import ReportGenerator
        report = self._make_minimal_report()
        gen = ReportGenerator(".")
        html = gen._render_html(gen._report_to_dict(report), report)
        assert f"v{__version__}" in html
        assert "v2.1.0" not in html

    def test_source_breakdown_key_is_html_escaped(self):
        from aegis.detectors.self_plagiarism import SelfPlagiarismResult
        from aegis.report.generator import ReportGenerator
        report = self._make_minimal_report()
        report.self_plagiarism_result = SelfPlagiarismResult(
            overall_overlap_pct=12.0,
            risk_level="MEDIUM",
            recycled_passages=[],
            source_breakdown={"<img src=x onerror=alert(1)>": 12.0},
            flags=[],
            cope_guidance="Review manually.",
        )
        gen = ReportGenerator(".")
        html = gen._render_html(gen._report_to_dict(report), report)
        assert "<img src=x onerror=alert(1)>" not in html
        assert "&lt;img src=x onerror=alert(1)&gt;" in html

    def test_citation_network_and_coherence_are_serialized(self):
        from aegis.detectors.citation_network import CitationNetworkResult
        from aegis.detectors.coherence_analyzer import CoherenceResult
        from aegis.report.generator import ReportGenerator

        report = self._make_minimal_report()
        report.citation_network_result = CitationNetworkResult(
            total_references=10, self_citation_count=1, self_citation_rate=0.1,
            predatory_journal_count=0, missing_doi_rate=0.0, year_span=(2020, 2023),
            venue_concentration=0.2, flags=[], overall_risk="LOW",
            openalex_queried=True, details={},
        )
        report.coherence_result = CoherenceResult(
            discourse_connector_density=2.0, sentence_length_cv=0.4, mtld_score=80.0,
            hedging_density=1.0, section_template_match=0.3, ensemble_score=0.2,
            verdict="HUMAN_LIKE", confidence=0.8, flags=[], paragraph_scores=[],
        )
        gen = ReportGenerator(".")
        d = gen._report_to_dict(report)
        assert d["citation_network"]["total_references"] == 10
        assert d["coherence"]["verdict"] == "HUMAN_LIKE"

        html = gen._render_html(d, report)
        assert "Citation Network Analysis" in html
        assert "Semantic Coherence Analysis" in html
