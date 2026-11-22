"""
Regression tests for false citation flags found by running AEGIS on a real
two-column Elsevier PDF (Biomedical Signal Processing and Control, 2026):

  - a DOI wrapped across lines was cut to "10.1016/j" and reported HALLUCINATED
  - page numbers after a wrapped DOI were glued on ("...09.002.15")
  - the running page header "... Control 115 (2026) 109428" was read as a
    reference's publication year
  - an author list or page range guessed as the "title" produced MISMATCH
    even though the reference text contains the real title
  - an online-first year (Nov 2022) was called a mismatch with the print
    issue year (2023)
"""

from types import SimpleNamespace

from aegis.core.document import DocumentParser
from aegis.detectors.citation import CitationIntegrityDetector


class TestDOIExtraction:

    def setup_method(self):
        self.p = DocumentParser()

    def test_wrapped_doi_is_rejoined(self):
        text = "EBioMedicine 77 (2022) 103911, https://doi.org/10.1016/j. \nebiom.2022.103911."
        assert self.p._extract_doi(text) == "10.1016/j.ebiom.2022.103911"

    def test_page_number_is_not_glued_on(self):
        text = "Int. J. 3 (2022) 1-9, https://doi.org/10.1016/j.ijin.2022.09.002. \n15 \n"
        assert self.p._extract_doi(text) == "10.1016/j.ijin.2022.09.002"

    def test_following_word_is_not_glued_on(self):
        assert self.p._extract_doi("doi:10.1234/abc.\nAccessed 2020") == "10.1234/abc"

    def test_unwrapped_doi_unchanged(self):
        assert self.p._extract_doi("see 10.1109/TSMCC.2011.2134847.") == "10.1109/TSMCC.2011.2134847"


class TestRunningHeadersInReferences:

    def test_repeated_page_header_does_not_become_the_year(self):
        header = "Biomedical Signal Processing and Control 115 (2026) 109428"
        body = "\n".join([header, "Intro text.", header, "Method text.", header])
        refs_text = (
            "References\n"
            "[1] V.S. Shanthi, Hybrid TABU search with SDS based feature selection, \n"
            + header + "\n"
            "Int. J. Intell. Netw. 3 (2022) 143-149.\n"
            "[2] A. Author, Another paper about lungs and ensembles, J. X 1 (2019) 1-2.\n"
        )
        refs = DocumentParser()._extract_references_heuristic(body + "\n" + refs_text)
        assert refs[0].year == "2022"
        assert "2026" not in refs[0].raw


def _verdict(raw, claimed_title, resolved_title, claimed_year="2022",
             resolved_year="2022", accepted_years=None):
    det = CitationIntegrityDetector(offline=True)
    ref = SimpleNamespace(cite_key="r1", raw=raw, year=claimed_year, authors=[], title=None)
    return det._build_comparison_verdict(
        ref, "10.1/x", raw, claimed_year, [], claimed_title,
        resolved_title, [], resolved_year, "J", "https://doi.org/10.1/x",
        accepted_years=accepted_years,
    )


class TestTitleAndYearComparison:

    def test_bad_title_guess_is_not_a_mismatch_when_real_title_is_present(self):
        raw = ("V.S. Shanthi, Hybrid TABU search with SDS based feature selec-\ntion "
               "for lung cancer prediction, Int. J. Intell. Netw. 3 (2022) 143-149.")
        v = _verdict(raw, "Shanthi, V.S",
                     "Hybrid TABU search with SDS based feature selection for lung cancer prediction")
        assert v.verdict == "VALID", v.issues

    def test_real_title_mismatch_is_still_caught(self):
        raw = "J. Doe, Quantum widgets for underwater basket weaving, J. Y 2 (2022) 1-5."
        v = _verdict(raw, "Quantum widgets for underwater basket weaving",
                     "Reduced Lung-Cancer Mortality with Low-Dose Computed Tomographic Screening")
        assert v.verdict in ("MISMATCH", "HALLUCINATED")

    def test_online_first_year_is_accepted(self):
        raw = "Y.H. Bhosale, PulDi-COVID classification, Biomed. Signal Process. Control 81 (Nov. 2022)."
        v = _verdict(raw, "PulDi-COVID classification", "PulDi-COVID classification",
                     claimed_year="2022", resolved_year="2023", accepted_years={"2023", "2022"})
        assert v.verdict == "VALID", v.issues

    def test_one_year_gap_is_a_note_not_a_mismatch(self):
        # Crossref sometimes records only the online-first date.
        v = _verdict("Z. Cai, Classification of lung cancer, Mol. Biosyst. 11 (Jan. 2015).",
                     "Classification of lung cancer", "Classification of lung cancer",
                     claimed_year="2015", resolved_year="2014", accepted_years={"2014"})
        assert v.verdict == "VALID"
        assert any("differs by one" in i for i in v.issues)

    def test_page_range_start_is_not_the_year(self):
        raw = ("K.M. Sunnetci, A. Alkan, Lung cancer detection, Int. J. Imaging Syst. "
               "Technol. 32 (6) (2022) 2049-2065, https://doi.org/10.1002/ima.22769")
        assert DocumentParser()._extract_year(raw) == "2022"

    def test_year_outside_all_crossref_dates_is_flagged(self):
        v = _verdict("A. B, Some title words here, J (2015).", "Some title words here",
                     "Some title words here", claimed_year="2015", resolved_year="2022",
                     accepted_years={"2022", "2021"})
        assert v.verdict == "MISMATCH"
        assert any("Year mismatch" in i for i in v.issues)
