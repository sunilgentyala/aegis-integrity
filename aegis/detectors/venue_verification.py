"""
Target Publisher Verification -- AEGIS Novel Feature #9.

Scopes citation integrity and duplicate-submission checks specifically to
six publishers commonly named in author queries: IEEE, ACM, Elsevier, IET,
IETE, and BCS. See aegis.detectors.publisher_registry for why this is
built on Crossref metadata rather than each publisher's own (mostly
paywalled or abstract-only) API -- none of them expose a free full-text
plagiarism-matching endpoint to outside tools.

Two independent checks, both free (no API key) and Crossref-only:

  1. Venue-claim verification (no extra network calls): reuses citation
     verdicts already resolved by CitationIntegrityDetector. If a raw
     reference string claims one of the six venues ("IEEE Trans...",
     "Proc. ACM...") but the DOI it cites actually resolves to a different
     publisher, that's a stronger and more specific signal than a generic
     title/author mismatch -- it means the citation is impersonating a
     venue, not just imprecisely transcribed.

  2. Prior-publication search (Crossref bibliographic search, scoped by
     member id where the venue is its own Crossref member, or by DOI
     prefix + container-title keywords for IETE/BCS which publish through
     Informa/OUP): finds near-identical titles already indexed under a
     target venue, i.e. the practical, legally available version of
     "check this against IEEE/ACM/Elsevier's corpus" -- title/abstract-
     level duplicate detection rather than full-text, since full text
     isn't accessible outside Crossref Similarity Check membership.
"""

from __future__ import annotations
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

import requests

from aegis.detectors.publisher_registry import (
    PublisherProfile,
    classify_publisher,
    claimed_publisher,
    claimed_publishers_all,
    resolve_target_publishers,
)

logger = logging.getLogger(__name__)


@dataclass
class VenueFlag:
    flag_type: str        # VENUE_MISMATCH | PRIOR_PUBLICATION_MATCH
    severity: str          # LOW | MEDIUM | HIGH
    message: str
    cite_key: Optional[str] = None
    data: dict = field(default_factory=dict)


@dataclass
class PriorPublicationMatch:
    publisher: str         # target-publisher key, e.g. "IEEE"
    title: str
    doi: Optional[str]
    year: Optional[str]
    title_similarity: float
    url: Optional[str]


@dataclass
class VenueVerificationResult:
    target_publishers: list[str]
    citations_by_publisher: dict[str, int]   # verified-citation counts per venue
    prior_publication_matches: list[PriorPublicationMatch]
    flags: list[VenueFlag]
    queried: bool                             # whether Crossref was actually contacted
    overall_risk: str                         # LOW | MEDIUM | HIGH


class TargetPublisherVerifier:
    """
    Venue-scoped citation authenticity + duplicate-submission checks
    against IEEE, ACM, Elsevier, IET, IETE, and BCS (configurable subset).
    """

    CROSSREF_BASE = "https://api.crossref.org/works"

    def __init__(
        self,
        target_publishers: Optional[list[str]] = None,
        email: str = "aegis-check@example.com",
        verify_timeout: float = 8.0,
        title_similarity_threshold: float = 0.75,
        offline: bool = False,
        max_workers: int = 6,
    ):
        self.profiles: list[PublisherProfile] = resolve_target_publishers(target_publishers)
        self.email = email
        self.timeout = verify_timeout
        self.title_sim_threshold = title_similarity_threshold
        self.offline = offline
        self.max_workers = max_workers
        self._session = None

    def _get_session(self):
        if self._session is None:
            session = requests.Session()
            session.headers.update({
                "User-Agent": f"AEGIS-IntegrityChecker/1.0 (mailto:{self.email})"
            })
            self._session = session
        return self._session

    # ------------------------------------------------------------------
    # 1. Venue-claim verification (no network -- reuses resolved citations)
    # ------------------------------------------------------------------

    def check_citation_claims(self, citation_verdicts: list) -> tuple[dict[str, int], list[VenueFlag]]:
        """
        citation_verdicts: list[CitationVerdict] already resolved by
        CitationIntegrityDetector.verify_references().

        Returns (citations_by_publisher, flags). Only verdicts with an
        actually-resolved record (VALID/MISMATCH) can be classified --
        HALLUCINATED/UNRESOLVABLE/NO_DOI citations have no resolved
        publisher to check against and are left out of both.
        """
        target_keys = {p.key for p in self.profiles}
        counts: dict[str, int] = {k: 0 for k in target_keys}
        flags: list[VenueFlag] = []

        for v in citation_verdicts:
            if v.verdict not in ("VALID", "MISMATCH"):
                continue
            actual = classify_publisher(v.doi, v.resolved_journal)
            if actual and actual in target_keys:
                counts[actual] += 1

            claimed = claimed_publisher(v.raw_text)
            claimed_all = claimed_publishers_all(v.raw_text)
            if (
                claimed and claimed in target_keys and claimed != actual
                and actual not in claimed_all
            ):
                profile = next(p for p in self.profiles if p.key == claimed)
                flags.append(VenueFlag(
                    flag_type="VENUE_MISMATCH",
                    severity="HIGH",
                    message=(
                        f"Reference '{v.cite_key}' reads as a {profile.display_name} "
                        f"publication, but its DOI resolves to "
                        f"{v.resolved_journal or 'a different publisher'}"
                        f"{f' ({actual})' if actual else ''}. "
                        "Possible venue misattribution or fabricated citation."
                    ),
                    cite_key=v.cite_key,
                    data={"claimed": claimed, "resolved": actual, "doi": v.doi},
                ))

        return counts, flags

    # ------------------------------------------------------------------
    # 2. Prior-publication search (Crossref, scoped per target venue)
    # ------------------------------------------------------------------

    def search_prior_publication(self, title: str) -> list[PriorPublicationMatch]:
        """
        For each configured target publisher, search Crossref for titles
        similar to `title` already published under that venue. Runs one
        request per publisher concurrently; a failure on one venue does
        not block the others.
        """
        if self.offline or not title or not self.profiles:
            return []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(self.profiles))) as pool:
            results = list(pool.map(lambda p: self._search_one_publisher(title, p), self.profiles))
        matches: list[PriorPublicationMatch] = []
        for r in results:
            matches.extend(r)
        matches.sort(key=lambda m: m.title_similarity, reverse=True)
        return matches

    def _search_one_publisher(self, title: str, profile: PublisherProfile) -> list[PriorPublicationMatch]:
        try:
            session = self._get_session()
            params = {
                "query.bibliographic": title[:200],
                "rows": 5 if profile.crossref_member_id is None else 3,
                "mailto": self.email,
            }
            if profile.crossref_member_id is not None:
                params["filter"] = f"member:{profile.crossref_member_id}"
            r = session.get(self.CROSSREF_BASE, params=params, timeout=self.timeout)
            if r.status_code != 200:
                return []
            items = r.json().get("message", {}).get("items", [])
        except Exception as ex:
            logger.debug("Prior-publication search failed for %s: %s", profile.key, ex)
            return []

        out: list[PriorPublicationMatch] = []
        for item in items:
            resolved_title = (item.get("title") or [""])[0]
            if not resolved_title:
                continue
            doi = item.get("DOI")
            container = (item.get("container-title") or [""])[0]

            # IETE/BCS share a DOI prefix with thousands of unrelated
            # Informa/OUP titles -- without their own Crossref member id,
            # container-title keywords are the only way to confirm a hit
            # actually belongs to the target venue rather than some other
            # journal under the same publisher.
            if profile.crossref_member_id is None:
                if not any(kw in container.lower() for kw in profile.container_keywords):
                    continue

            sim = self._title_similarity(title, resolved_title)
            if sim < self.title_sim_threshold:
                continue

            year = None
            for date_field in ("published-print", "published-online", "issued"):
                dp = item.get(date_field, {}).get("date-parts", [[]])
                if dp and dp[0]:
                    year = str(dp[0][0])
                    break

            out.append(PriorPublicationMatch(
                publisher=profile.key,
                title=resolved_title,
                doi=doi,
                year=year,
                title_similarity=round(sim, 3),
                url=item.get("URL", f"https://doi.org/{doi}" if doi else None),
            ))
        return out

    def _title_similarity(self, a: str, b: str) -> float:
        words_a = set(re.findall(r"\b[a-z]{3,}\b", a.lower()))
        words_b = set(re.findall(r"\b[a-z]{3,}\b", b.lower()))
        if not words_a or not words_b:
            return 0.0
        inter = len(words_a & words_b)
        union = len(words_a | words_b)
        return inter / union if union else 0.0

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def analyze(
        self,
        title: Optional[str],
        citation_verdicts: list,
    ) -> VenueVerificationResult:
        counts, claim_flags = self.check_citation_claims(citation_verdicts)

        prior_matches = self.search_prior_publication(title) if title else []
        queried = not self.offline and bool(title) and bool(self.profiles)

        match_flags = [
            VenueFlag(
                flag_type="PRIOR_PUBLICATION_MATCH",
                severity="HIGH" if m.title_similarity >= 0.90 else "MEDIUM",
                message=(
                    f"A {m.title_similarity:.0%}-similar title is already indexed "
                    f"under {m.publisher}: \"{m.title[:100]}\""
                    f"{f' ({m.year})' if m.year else ''}. Possible duplicate or "
                    "prior submission to this venue -- verify this isn't the same "
                    "work, or disclose it as a prior/related publication."
                ),
                data={"doi": m.doi, "title": m.title, "publisher": m.publisher,
                      "similarity": m.title_similarity, "url": m.url},
            )
            for m in prior_matches
        ]

        all_flags = claim_flags + match_flags
        high_count = sum(1 for f in all_flags if f.severity == "HIGH")
        if high_count > 0:
            risk = "HIGH"
        elif all_flags:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return VenueVerificationResult(
            target_publishers=[p.key for p in self.profiles],
            citations_by_publisher=counts,
            prior_publication_matches=prior_matches,
            flags=all_flags,
            queried=queried,
            overall_risk=risk,
        )
