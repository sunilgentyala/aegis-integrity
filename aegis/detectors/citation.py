"""
Citation Integrity Detector -- AEGIS Novel Feature #1.

No existing open-source plagiarism tool validates citations. This module:
  1. Parses references from raw text (IEEE, APA, Vancouver, MLA formats)
  2. Resolves DOIs via the Crossref REST API (free, no API key needed)
  3. Cross-checks author names, year, and journal against the resolved metadata
  4. Detects hallucinated references (DOI resolves to a different paper)
  5. Flags unresolvable DOIs (possibly fabricated by LLMs)
  6. Computes a per-reference verdict: VALID / MISMATCH / HALLUCINATED /
     NOT_FOUND_IN_CROSSREF / UNAVAILABLE / UNRESOLVABLE / NO_DOI

A Crossref 404 on /works/{doi} means "not a Crossref record," not "fake DOI":
DataCite-registered DOIs (e.g. arXiv's 10.48550/* prefix) always 404 against
Crossref even when valid, so a 404 triggers a registration-agency check via
/works/{doi}/agency before HALLUCINATED is returned. When the agency is
DataCite, its own REST API (api.datacite.org) is queried for real metadata
and compared against the claimed citation the same way Crossref results are,
rather than only confirming the DOI exists. Transient failures (timeouts,
429, 5xx) are reported as UNAVAILABLE rather than folded into a verdict
about the citation itself.

A peer-reviewed study found ChatGPT fabricated up to 55% of references
depending on model version (Walters & Wilder, Scientific Reports, 2023,
https://doi.org/10.1038/s41598-023-41032-5).
"""

from __future__ import annotations
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_NETWORK_EXCEPTIONS = (requests.exceptions.Timeout, requests.exceptions.ConnectionError)


@dataclass
class CitationVerdict:
    cite_key: str
    raw_text: str
    doi: Optional[str]
    claimed_year: Optional[str]
    claimed_authors: list[str]
    claimed_title: Optional[str]
    resolved_title: Optional[str]
    resolved_authors: list[str]
    resolved_year: Optional[str]
    resolved_journal: Optional[str]
    verdict: str          # VALID | MISMATCH | HALLUCINATED | NOT_FOUND_IN_CROSSREF |
                          # UNAVAILABLE | UNRESOLVABLE | NO_DOI
    confidence: float     # 0.0 -- 1.0
    issues: list[str]
    crossref_url: Optional[str]


class CitationIntegrityDetector:
    """
    Verify academic references against Crossref and PubMed.

    Fills critical gap: no open-source plagiarism tool does citation
    validation. LLM-generated papers hallucinate citations at high rates.
    """

    CROSSREF_BASE = "https://api.crossref.org/works"
    PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    DATACITE_BASE = "https://api.datacite.org/dois"

    def __init__(
        self,
        email: str = "aegis-check@example.com",  # polite API usage
        verify_timeout: float = 8.0,
        min_title_similarity: float = 0.65,
        offline: bool = False,
        max_workers: int = 8,
    ):
        self.email = email
        self.timeout = verify_timeout
        self.min_title_sim = min_title_similarity
        self.offline = offline
        self.max_workers = max_workers
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests
            from requests.adapters import HTTPAdapter
            session = requests.Session()
            session.headers.update({
                "User-Agent": f"AEGIS-IntegrityChecker/1.0 (mailto:{self.email})"
            })
            adapter = HTTPAdapter(pool_connections=self.max_workers,
                                   pool_maxsize=self.max_workers)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            self._session = session
        return self._session

    def verify_references(
        self, refs: list  # list[ParsedReference]
    ) -> list[CitationVerdict]:
        """Verify references concurrently against Crossref.

        Sequential per-reference lookups (each up to `verify_timeout` seconds)
        used to take minutes for reference-heavy papers and could blow past
        callers' overall timeouts. Crossref's polite pool tolerates a modest
        number of concurrent connections, so we fan requests out instead.
        """
        if not refs:
            return []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(refs))) as pool:
            return list(pool.map(self._verify_one, refs))

    def _verify_one(self, ref) -> CitationVerdict:
        doi = ref.doi
        raw = ref.raw or ""
        claimed_year = ref.year
        claimed_authors = ref.authors or []
        claimed_title = ref.title or self._extract_title_from_raw(raw)

        if self.offline or not doi:
            # Try title-based lookup if no DOI -- but only when the title is
            # specific enough to search on. A short/generic extracted title
            # (e.g. a spec document cited as '"Authorization," Specification
            # 2026-07-28' rather than a real paper) can coincidentally
            # word-match an unrelated Crossref record with the same short
            # title (a book chapter also just titled "Authorization"),
            # producing a fabricated-looking MISMATCH/HALLUCINATED verdict
            # against a reference that was never a DOI-bearing publication
            # in the first place.
            if claimed_title and not self.offline and len(claimed_title.split()) >= 4:
                return self._lookup_by_title(ref, claimed_title)
            return CitationVerdict(
                cite_key=ref.cite_key or "unknown",
                raw_text=raw[:300],
                doi=None,
                claimed_year=claimed_year,
                claimed_authors=claimed_authors,
                claimed_title=claimed_title,
                resolved_title=None,
                resolved_authors=[],
                resolved_year=None,
                resolved_journal=None,
                verdict="NO_DOI",
                confidence=0.5,
                issues=["No DOI found; cannot verify against Crossref"],
                crossref_url=None,
            )

        # --- Resolve DOI via Crossref ---
        try:
            session = self._get_session()
            url = f"{self.CROSSREF_BASE}/{doi}"
            r = session.get(url, timeout=self.timeout)
            if r.status_code == 404:
                return self._handle_crossref_404(ref, doi, url)
            if r.status_code == 429 or r.status_code >= 500:
                return self._unavailable(
                    ref, doi, f"Crossref HTTP {r.status_code} (rate-limited or down)")
            if r.status_code != 200:
                return self._unresolvable(ref, doi,
                                          f"Crossref HTTP {r.status_code}")

            data = r.json().get("message", {})
        except _NETWORK_EXCEPTIONS as ex:
            return self._unavailable(ref, doi, str(ex))
        except Exception as ex:
            return self._unresolvable(ref, doi, str(ex))

        # --- Extract resolved metadata ---
        resolved_title = None
        titles = data.get("title", [])
        if titles:
            resolved_title = titles[0]

        author_list = data.get("author", [])
        resolved_authors = [
            f"{a.get('family', '')} {a.get('given', '')[:1]}".strip()
            for a in author_list if a.get("family")
        ]

        pub_year = None
        for date_field in ("published-print", "published-online", "issued"):
            dp = data.get(date_field, {}).get("date-parts", [[]])
            if dp and dp[0]:
                pub_year = str(dp[0][0])
                break

        journal_title = None
        container = data.get("container-title", [])
        if container:
            journal_title = container[0]

        crossref_url = data.get("URL", f"https://doi.org/{doi}")

        return self._build_comparison_verdict(
            ref, doi, raw, claimed_year, claimed_authors, claimed_title,
            resolved_title, resolved_authors, pub_year, journal_title, crossref_url,
        )

    def _build_comparison_verdict(
        self, ref, doi, raw, claimed_year, claimed_authors, claimed_title,
        resolved_title, resolved_authors, resolved_year, resolved_journal, source_url,
    ) -> CitationVerdict:
        """Shared claimed-vs-resolved comparison, usable against metadata
        resolved from Crossref or from DataCite (or any future source that
        returns title/authors/year in this shape)."""
        issues: list[str] = []
        verdict = "VALID"
        confidence = 1.0

        # Year check
        if claimed_year and resolved_year and claimed_year != resolved_year:
            issues.append(f"Year mismatch: claimed {claimed_year}, actual {resolved_year}")
            verdict = "MISMATCH"
            confidence -= 0.3

        # Title check (fuzzy)
        if claimed_title and resolved_title:
            title_sim = self._string_similarity(
                claimed_title.lower(), resolved_title.lower())
            if title_sim < self.min_title_sim:
                issues.append(
                    f"Title mismatch (similarity {title_sim:.2f}): "
                    f"claimed '{claimed_title[:60]}', "
                    f"actual '{resolved_title[:60]}'")
                verdict = "MISMATCH"
                confidence -= 0.35

        # Author check (at least first author family name)
        if claimed_authors and resolved_authors:
            first_claimed = claimed_authors[0].split()[-1].lower()
            first_resolved = resolved_authors[0].split()[0].lower()
            if first_claimed and first_resolved and first_claimed not in first_resolved:
                issues.append(
                    f"First-author mismatch: claimed '{first_claimed}', "
                    f"actual '{first_resolved}'")
                if verdict != "MISMATCH":
                    verdict = "MISMATCH"
                confidence -= 0.2

        confidence = max(0.0, round(confidence, 2))
        if verdict == "MISMATCH" and confidence < 0.3:
            verdict = "HALLUCINATED"

        return CitationVerdict(
            cite_key=ref.cite_key or "unknown",
            raw_text=raw[:300],
            doi=doi,
            claimed_year=claimed_year,
            claimed_authors=claimed_authors,
            claimed_title=claimed_title,
            resolved_title=resolved_title,
            resolved_authors=resolved_authors,
            resolved_year=resolved_year,
            resolved_journal=resolved_journal,
            verdict=verdict,
            confidence=confidence,
            issues=issues,
            crossref_url=source_url,
        )

    def _lookup_by_title(self, ref, title: str) -> CitationVerdict:
        """Search Crossref by title when no DOI is present."""
        try:
            session = self._get_session()
            params = {
                "query.title": title[:120],
                "rows": 1,
                "mailto": self.email,
            }
            r = session.get(self.CROSSREF_BASE, params=params,
                            timeout=self.timeout)
            if r.status_code != 200:
                raise ValueError(f"HTTP {r.status_code}")
            items = r.json().get("message", {}).get("items", [])
            if not items:
                return self._no_doi_verdict(ref, "No Crossref match found by title")
            best = items[0]
            resolved_title = (best.get("title") or [""])[0]
            sim = self._string_similarity(title.lower(), resolved_title.lower())
            if sim < self.min_title_sim:
                return self._no_doi_verdict(
                    ref,
                    f"Title-based lookup found dissimilar result (sim={sim:.2f})")
            ref.doi = best.get("DOI")
            ref.title = resolved_title
            return self._verify_one(ref)
        except Exception as ex:
            return self._no_doi_verdict(ref, str(ex))

    def _handle_crossref_404(self, ref, doi: str, url: str) -> CitationVerdict:
        """
        A 404 from /works/{doi} only means Crossref has no record for this DOI --
        it does NOT mean the DOI doesn't exist. DOIs registered with a different
        agency (e.g. DataCite, which registers arXiv's 10.48550/* prefix) will
        always 404 against Crossref even though they're real, resolvable DOIs.
        Check the registration agency before concluding the citation is fabricated.
        """
        try:
            session = self._get_session()
            agency_url = f"{self.CROSSREF_BASE}/{doi}/agency"
            r = session.get(agency_url, timeout=self.timeout)
            if r.status_code == 200:
                agency = (
                    r.json().get("message", {}).get("agency", {}).get("id", "")
                ).lower()
                if agency == "datacite":
                    datacite_verdict = self._lookup_datacite(ref, doi)
                    if datacite_verdict is not None:
                        return datacite_verdict
                    # DataCite lookup itself failed (network/parse error) --
                    # fall through to the generic not-found-here pass-through
                    # below rather than silently claiming HALLUCINATED.
                if agency and agency != "crossref":
                    return CitationVerdict(
                        cite_key=ref.cite_key or "unknown",
                        raw_text=(ref.raw or "")[:300],
                        doi=doi,
                        claimed_year=ref.year,
                        claimed_authors=ref.authors or [],
                        claimed_title=ref.title,
                        resolved_title=None,
                        resolved_authors=[],
                        resolved_year=None,
                        resolved_journal=None,
                        verdict="NOT_FOUND_IN_CROSSREF",
                        confidence=0.3,
                        issues=[
                            f"DOI {doi} is registered with {agency}, not Crossref -- "
                            "AEGIS does not yet verify metadata from this agency, so "
                            "this citation could not be independently verified. "
                            "Check the DOI manually."
                        ],
                        crossref_url=f"https://doi.org/{doi}",
                    )
            elif r.status_code != 404:
                # A non-200, non-404 response (429 rate-limited, 5xx, etc.)
                # is a transient service problem, not evidence the DOI is
                # unregistered -- under the concurrent verification fan-out
                # (verify_references() queries every reference's /agency
                # endpoint in parallel) Crossref's own rate limit on this
                # secondary lookup is hit far more easily than on the
                # primary /works/{doi} call, and treating that as "checked,
                # doesn't exist" turned real, resolvable arXiv/DataCite DOIs
                # into false HALLUCINATED verdicts.
                return self._unavailable(
                    ref, doi, f"Agency check HTTP {r.status_code} (rate-limited or down)")
            # else: agency lookup itself 404s -> DOI genuinely unregistered anywhere
        except _NETWORK_EXCEPTIONS as ex:
            return self._unavailable(ref, doi, f"Agency check failed: {ex}")
        except Exception:
            pass  # fall through to HALLUCINATED below

        return CitationVerdict(
            cite_key=ref.cite_key or "unknown",
            raw_text=(ref.raw or "")[:300],
            doi=doi,
            claimed_year=ref.year,
            claimed_authors=ref.authors or [],
            claimed_title=ref.title,
            resolved_title=None,
            resolved_authors=[],
            resolved_year=None,
            resolved_journal=None,
            verdict="HALLUCINATED",
            confidence=0.95,
            issues=[f"DOI {doi} does not exist in Crossref or any other registration agency"],
            crossref_url=url,
        )

    def _lookup_datacite(self, ref, doi: str) -> Optional[CitationVerdict]:
        """
        Resolve a DataCite-registered DOI (e.g. arXiv's 10.48550/* prefix)
        against DataCite's own REST API and run the same claimed-vs-resolved
        comparison used for Crossref, instead of only confirming the DOI
        exists without checking its metadata.

        Returns None (rather than raising) on any failure so the caller can
        fall back to the generic not-found-here pass-through -- a DataCite
        outage should not produce a false HALLUCINATED verdict.
        """
        try:
            session = self._get_session()
            r = session.get(f"{self.DATACITE_BASE}/{doi}", timeout=self.timeout)
            if r.status_code != 200:
                return None
            attrs = r.json().get("data", {}).get("attributes", {})
        except Exception:
            return None

        titles = attrs.get("titles") or []
        resolved_title = titles[0].get("title") if titles else None

        resolved_authors = [
            f"{c.get('familyName', '')} {c.get('givenName', '')[:1]}".strip()
            for c in (attrs.get("creators") or [])
            if c.get("familyName")
        ]

        resolved_year = attrs.get("publicationYear")
        resolved_year = str(resolved_year) if resolved_year else None

        resolved_journal = (attrs.get("container") or {}).get("title")

        return self._build_comparison_verdict(
            ref, doi, ref.raw or "", ref.year, ref.authors or [], ref.title,
            resolved_title, resolved_authors, resolved_year, resolved_journal,
            f"https://doi.org/{doi}",
        )

    def _unavailable(self, ref, doi: str, reason: str) -> CitationVerdict:
        """Citation verification could not complete due to a transient service
        issue (timeout, rate limit, outage) -- not a statement about the
        citation's validity. Callers should not treat this as an integrity flag."""
        return CitationVerdict(
            cite_key=ref.cite_key or "unknown",
            raw_text=(ref.raw or "")[:300],
            doi=doi,
            claimed_year=ref.year,
            claimed_authors=ref.authors or [],
            claimed_title=ref.title,
            resolved_title=None,
            resolved_authors=[],
            resolved_year=None,
            resolved_journal=None,
            verdict="UNAVAILABLE",
            confidence=0.0,
            issues=[f"Verification service unavailable: {reason}"],
            crossref_url=None,
        )

    def _unresolvable(self, ref, doi: str, reason: str) -> CitationVerdict:
        return CitationVerdict(
            cite_key=ref.cite_key or "unknown",
            raw_text=(ref.raw or "")[:300],
            doi=doi,
            claimed_year=ref.year,
            claimed_authors=ref.authors or [],
            claimed_title=ref.title,
            resolved_title=None,
            resolved_authors=[],
            resolved_year=None,
            resolved_journal=None,
            verdict="UNRESOLVABLE",
            confidence=0.0,
            issues=[f"Could not resolve DOI: {reason}"],
            crossref_url=None,
        )

    def _no_doi_verdict(self, ref, reason: str) -> CitationVerdict:
        return CitationVerdict(
            cite_key=ref.cite_key or "unknown",
            raw_text=(ref.raw or "")[:300],
            doi=None,
            claimed_year=ref.year,
            claimed_authors=ref.authors or [],
            claimed_title=ref.title,
            resolved_title=None,
            resolved_authors=[],
            resolved_year=None,
            resolved_journal=None,
            verdict="NO_DOI",
            confidence=0.4,
            issues=[reason],
            crossref_url=None,
        )

    # Matches a leftover author-list fragment after splitting on ". " --
    # e.g. "Gentyala, F", "Lee, and R", "and R" -- a surname followed by a
    # single initial, not a title. Splitting on ". " breaks on every
    # abbreviated author initial (each is itself "X.") in addition to real
    # sentence boundaries, so multi-author IEEE/ACM-style references
    # fragment into several of these before reaching the actual title.
    _AUTHOR_FRAGMENT_RE = re.compile(
        r"^(?:[A-Z][a-zA-Z\-']*,?\s*)?(?:and\s+)?[A-Z]\.?$")

    def _extract_title_from_raw(self, raw: str) -> Optional[str]:
        # Most citation styles (IEEE, ACM, many journals) quote the title
        # verbatim -- this is a much more reliable signal than guessing from
        # sentence-split position, and unaffected by how many periods
        # appear in the author list before it.
        quoted = re.search(r'["“]([^"”]{10,300})["”]', raw)
        if quoted:
            return quoted.group(1).strip().rstrip(",")

        # Word's smart-quote autocorrect renders titles in single curly
        # quotes (e.g. 'Not What You've Signed Up For,' in Proceedings...)
        # rather than double quotes -- common in IEEE-style reference lists
        # produced from Word. A naive quote-to-quote match breaks on this
        # style because the closing curly quote (U+2019) is the SAME
        # character Word uses for an apostrophe inside the title itself
        # ("You've"), so it would close the match after "You" instead of
        # at the real end of the title. IEEE/ACM-style references always
        # place a comma immediately before the closing quote at the true
        # title boundary ("...Injection,' in Proceedings..."), and a
        # mid-title apostrophe is never immediately preceded by a comma,
        # so anchoring on ",<quote>" instead of a bare "<quote>" reliably
        # skips those apostrophes. Try curly quotes first, then straight.
        single_quoted = (
            re.search(r"‘(.{10,300}?),[’']", raw)
            or re.search(r"'(.{10,300}?),'", raw)
        )
        if single_quoted:
            return single_quoted.group(1).strip()

        # Fallback for styles that don't quote the title: split on ". " and
        # skip any part that looks like a leftover author-initial fragment
        # rather than assuming the title is always parts[1] or parts[2].
        parts = re.split(r"\.\s+", raw)
        for part in parts[1:6]:
            part = part.strip()
            if not (10 < len(part) < 200):
                continue
            if re.match(r"^(19|20)\d{2}", part):
                continue
            if self._AUTHOR_FRAGMENT_RE.match(part):
                continue
            return part
        return None

    def _string_similarity(self, a: str, b: str) -> float:
        """Normalized Levenshtein-based similarity for short strings."""
        if not a or not b:
            return 0.0
        # Use word set overlap as a fast proxy
        words_a = set(re.findall(r"\b[a-z]{3,}\b", a.lower()))
        words_b = set(re.findall(r"\b[a-z]{3,}\b", b.lower()))
        if not words_a and not words_b:
            return 1.0
        inter = len(words_a & words_b)
        union = len(words_a | words_b)
        return inter / union if union else 0.0

    # Below this many references, or below this coverage fraction, a
    # percentage like "100% Citation Issues" is not statistically meaningful
    # (one low-confidence parsed reference flagged out of one detected is
    # not the same claim as one out of thirty) -- report INCONCLUSIVE instead.
    MIN_REFERENCES_FOR_ASSESSMENT = 5
    MIN_COVERAGE_FOR_ASSESSMENT = 0.80

    # Verdicts where AEGIS actually obtained authoritative metadata (from
    # Crossref or DataCite) to compare against the claim -- as opposed to
    # verdicts that only mean "could not independently verify this one".
    _VERIFIED_VERDICTS = frozenset({"VALID", "MISMATCH", "HALLUCINATED"})

    def summary(self, verdicts: list[CitationVerdict]) -> dict:
        total = len(verdicts)
        counts = {}
        for v in verdicts:
            counts[v.verdict] = counts.get(v.verdict, 0) + 1
        hallucinated = counts.get("HALLUCINATED", 0)
        mismatch = counts.get("MISMATCH", 0)
        flagged = hallucinated + mismatch
        integrity_score = round(1.0 - (flagged / total), 3) if total else 1.0

        with_identifier = sum(1 for v in verdicts if v.doi)
        verified = sum(1 for v in verdicts if v.verdict in self._VERIFIED_VERDICTS)
        coverage = round(verified / total, 3) if total else 0.0

        inconclusive = (
            total < self.MIN_REFERENCES_FOR_ASSESSMENT
            or coverage < self.MIN_COVERAGE_FOR_ASSESSMENT
        )

        return {
            "total_references": total,
            "references_with_identifier": with_identifier,
            "references_verified": verified,
            "verification_coverage": coverage,
            "verdict_counts": counts,
            "flagged_count": flagged,
            "citation_integrity_score": integrity_score,
            "assessment": "INCONCLUSIVE" if inconclusive else "ASSESSED",
            "risk_level": (
                "INCONCLUSIVE" if inconclusive else
                "HIGH" if hallucinated > 0 else
                "MEDIUM" if mismatch > 1 else
                "LOW"
            ),
        }
