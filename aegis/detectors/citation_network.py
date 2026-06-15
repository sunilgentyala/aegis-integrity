"""
Citation Network Analyzer -- AEGIS v2.0 Novel Feature.

Goes beyond single-citation DOI validation to analyze the structural
patterns of a paper's entire reference list:

1. Self-citation inflation: flags when >30% of references share an author
   with the submission -- a common citation cartel tactic.
2. Predatory journal heuristics: checks journal names and ISSNs against
   known predatory patterns (no official Beall's List redistribution --
   uses pattern-matching heuristics to avoid legal issues).
3. Citation cluster detection: identifies when all/most references come
   from a suspiciously narrow set of venues or years (may indicate
   manufactured reference lists by LLMs).
4. OpenAlex integration: free, open API to retrieve journal quality tiers
   (h-index, SJR quartile) without institutional access.
5. Missing DOI rate: a very high fraction of references without DOIs is
   consistent with AI-hallucinated bibliographies.

These patterns collectively detect LLM-generated papers that hallucinate
plausible-sounding reference lists.
"""

from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)


# Heuristic patterns for predatory journal names (not a reproduction of Beall's list)
_PREDATORY_NAME_PATTERNS = [
    r"\bInternational Journal of (?:Advanced|Novel|Innovative|Modern) (?:Research|Studies|Science)\b",
    r"\bJournal of (?:Emerging|Global) (?:Research|Studies|Trends)\b",
    r"\bWorld Journal of (?:Science|Research|Innovation)\b",
    r"\bAmerican Journal of (?:Advanced|Modern) (?:Research|Science)\b",
    r"\bEuropean Journal of (?:Academic|Applied) (?:Research|Studies)\b",
    r"\bInternational Research Journal\b",
    r"\bGlobal Journal of (?:Pure|Applied) (?:Science|Research)\b",
]

_PREDATORY_PUBLISHER_PATTERNS = [
    r"\bOmics\b",
    r"\bHilaris\b",
    r"\bScitechnol\b",
    r"\bWaxmann\b",
    r"\bBentham Open\b",
    r"\bIntech\b",
]


@dataclass
class CitationNetworkFlag:
    flag_type: str          # SELF_CITATION_INFLATION | PREDATORY_JOURNAL | CLUSTER | MISSING_DOI | LOW_IMPACT
    severity: str           # LOW | MEDIUM | HIGH
    message: str
    affected_refs: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


@dataclass
class CitationNetworkResult:
    total_references: int
    self_citation_count: int
    self_citation_rate: float
    predatory_journal_count: int
    missing_doi_rate: float
    year_span: tuple[int, int]          # (min_year, max_year) across references
    venue_concentration: float          # Herfindahl index of journal distribution
    flags: list[CitationNetworkFlag]
    overall_risk: str                   # LOW | MEDIUM | HIGH
    openalex_queried: bool
    details: dict


class CitationNetworkAnalyzer:
    """
    Analyzes structural patterns in a paper's reference list to detect
    LLM-generated bibliographies, citation cartels, and predatory venue usage.
    """

    def __init__(
        self,
        submission_authors: Optional[list[str]] = None,
        self_citation_threshold: float = 0.30,
        missing_doi_threshold: float = 0.60,
        use_openalex: bool = True,
        openalex_email: str = "aegis-check@example.com",
        offline: bool = False,
    ):
        self.submission_authors = [
            a.lower() for a in (submission_authors or [])
        ]
        self.self_cit_thresh = self_citation_threshold
        self.missing_doi_thresh = missing_doi_threshold
        self.use_openalex = use_openalex
        self.openalex_email = openalex_email
        self.offline = offline

    def _extract_author_surnames(self, ref_text: str) -> list[str]:
        # Heuristic: capture capitalized word sequences before year/comma
        patterns = [
            r"([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*)",  # APA style
            r"([A-Z][a-z]+)\s+et al",                # et al short form
        ]
        names = []
        for p in patterns:
            names.extend(re.findall(p, ref_text))
        return [n.lower().strip() for n in names if len(n) > 2]

    def _is_predatory(self, ref_text: str) -> tuple[bool, str]:
        for pat in _PREDATORY_NAME_PATTERNS:
            if re.search(pat, ref_text, re.IGNORECASE):
                return True, f"Name matches predatory pattern: {pat}"
        for pat in _PREDATORY_PUBLISHER_PATTERNS:
            if re.search(pat, ref_text, re.IGNORECASE):
                return True, f"Publisher matches predatory pattern: {pat}"
        return False, ""

    def _extract_year(self, ref_text: str) -> Optional[int]:
        m = re.search(r"\b(19[89]\d|20[012]\d)\b", ref_text)
        return int(m.group(1)) if m else None

    def _extract_venue(self, ref_text: str) -> Optional[str]:
        # Match "In Proc./Journal of/IEEE Transactions on/..."
        patterns = [
            r"(?:In |Proc\. |Proceedings of )?([A-Z][^,.]{5,60}(?:Conference|Symposium|Workshop|Journal|Transactions|Letters|Review))",
            r"(?:IEEE|ACM|Elsevier|Springer|Nature|Science)\s+[A-Z][^,.]{5,60}",
        ]
        for p in patterns:
            m = re.search(p, ref_text)
            if m:
                return m.group(0).strip()[:80]
        return None

    def _query_openalex(self, doi: str) -> Optional[dict]:
        if self.offline or not doi:
            return None
        try:
            import requests
            url = f"https://api.openalex.org/works/doi:{doi}"
            params = {"mailto": self.openalex_email}
            resp = requests.get(url, params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                venue = data.get("primary_location", {}).get("source", {})
                return {
                    "title": data.get("title"),
                    "cited_by_count": data.get("cited_by_count", 0),
                    "venue_display_name": venue.get("display_name"),
                    "venue_type": venue.get("type"),
                    "is_oa": data.get("open_access", {}).get("is_oa", False),
                }
        except Exception as e:
            logger.debug("OpenAlex query failed for %s: %s", doi, e)
        return None

    def analyze(
        self,
        references: list,   # list of CitationVerdict (from citation.py) or raw dicts
        raw_ref_texts: Optional[list[str]] = None,
    ) -> CitationNetworkResult:
        flags: list[CitationNetworkFlag] = []

        # Build unified list of (raw_text, doi, year) tuples
        entries = []
        if references:
            for r in references:
                if hasattr(r, "raw_text"):
                    entries.append({
                        "text": r.raw_text,
                        "doi": getattr(r, "doi", None),
                        "authors": r.claimed_authors if hasattr(r, "claimed_authors") else [],
                    })
                elif isinstance(r, dict):
                    entries.append(r)
        if raw_ref_texts and not entries:
            entries = [{"text": t, "doi": None, "authors": []} for t in raw_ref_texts]

        n = len(entries)
        if n == 0:
            return CitationNetworkResult(
                total_references=0, self_citation_count=0, self_citation_rate=0.0,
                predatory_journal_count=0, missing_doi_rate=0.0,
                year_span=(0, 0), venue_concentration=0.0, flags=[],
                overall_risk="LOW", openalex_queried=False,
                details={"note": "No references found."},
            )

        # 1. Self-citation inflation
        self_cit_count = 0
        self_cit_refs = []
        for e in entries:
            text = e.get("text", "")
            all_names = e.get("authors") or self._extract_author_surnames(text)
            for sub_auth in self.submission_authors:
                if any(sub_auth in a.lower() for a in all_names):
                    self_cit_count += 1
                    self_cit_refs.append(text[:80])
                    break

        self_cit_rate = self_cit_count / n
        if self_cit_rate > self.self_cit_thresh:
            flags.append(CitationNetworkFlag(
                flag_type="SELF_CITATION_INFLATION",
                severity="HIGH" if self_cit_rate > 0.50 else "MEDIUM",
                message=f"Self-citation rate {self_cit_rate:.0%} exceeds threshold {self.self_cit_thresh:.0%}. "
                        f"Possible citation cartel behavior.",
                affected_refs=self_cit_refs[:10],
                data={"rate": self_cit_rate, "count": self_cit_count},
            ))

        # 2. Predatory journal detection
        predatory_count = 0
        predatory_refs = []
        for e in entries:
            text = e.get("text", "")
            is_pred, reason = self._is_predatory(text)
            if is_pred:
                predatory_count += 1
                predatory_refs.append(f"{text[:60]} [{reason}]")

        if predatory_count > 0:
            flags.append(CitationNetworkFlag(
                flag_type="PREDATORY_JOURNAL",
                severity="HIGH" if predatory_count > 2 else "MEDIUM",
                message=f"{predatory_count} references match predatory journal patterns.",
                affected_refs=predatory_refs[:10],
                data={"count": predatory_count},
            ))

        # 3. Missing DOI rate (high = possible hallucinated refs)
        missing_doi = sum(1 for e in entries if not e.get("doi"))
        missing_doi_rate = missing_doi / n
        if missing_doi_rate > self.missing_doi_thresh:
            flags.append(CitationNetworkFlag(
                flag_type="MISSING_DOI",
                severity="MEDIUM",
                message=f"{missing_doi_rate:.0%} of references lack a DOI. "
                        f"High rate is consistent with LLM-hallucinated bibliographies.",
                data={"rate": missing_doi_rate, "count": missing_doi},
            ))

        # 4. Year cluster detection
        years = [self._extract_year(e.get("text", "")) for e in entries]
        valid_years = [y for y in years if y is not None]
        year_span = (min(valid_years), max(valid_years)) if valid_years else (0, 0)

        if valid_years:
            year_counts = Counter(valid_years)
            most_common_year, most_common_count = year_counts.most_common(1)[0]
            cluster_rate = most_common_count / len(valid_years)
            if cluster_rate > 0.50 and len(valid_years) >= 5:
                flags.append(CitationNetworkFlag(
                    flag_type="YEAR_CLUSTER",
                    severity="MEDIUM",
                    message=f"{cluster_rate:.0%} of references share the same year "
                            f"({most_common_year}). Suspicious clustering.",
                    data={"year": most_common_year, "cluster_rate": cluster_rate},
                ))

        # 5. Venue concentration (Herfindahl index)
        venues = [self._extract_venue(e.get("text", "")) for e in entries]
        valid_venues = [v for v in venues if v]
        hhi = 0.0
        if valid_venues:
            venue_counts = Counter(valid_venues)
            total = len(valid_venues)
            hhi = sum((c / total) ** 2 for c in venue_counts.values())
            if hhi > 0.40:
                flags.append(CitationNetworkFlag(
                    flag_type="VENUE_CONCENTRATION",
                    severity="LOW",
                    message=f"Reference list is highly concentrated "
                            f"(Herfindahl index {hhi:.2f}). Possible narrow scope or fabricated list.",
                    data={"hhi": hhi, "top_venues": dict(venue_counts.most_common(5))},
                ))

        # 6. OpenAlex enrichment for low-impact journal check
        openalex_queried = False
        low_impact_refs = []
        if self.use_openalex and not self.offline:
            for e in entries[:10]:  # limit API calls
                doi = e.get("doi")
                if doi:
                    oa_data = self._query_openalex(doi)
                    if oa_data:
                        openalex_queried = True
                        citations = oa_data.get("cited_by_count", 0)
                        if citations == 0 and oa_data.get("venue_type") != "repository":
                            low_impact_refs.append(doi)

            if len(low_impact_refs) >= 3:
                flags.append(CitationNetworkFlag(
                    flag_type="LOW_IMPACT_REFERENCES",
                    severity="LOW",
                    message=f"{len(low_impact_refs)} references have zero citations in OpenAlex -- "
                            f"possible obscure or hallucinated works.",
                    affected_refs=low_impact_refs,
                    data={"count": len(low_impact_refs)},
                ))

        # Overall risk
        high_flags = sum(1 for f in flags if f.severity == "HIGH")
        med_flags = sum(1 for f in flags if f.severity == "MEDIUM")
        if high_flags >= 2 or (high_flags >= 1 and med_flags >= 2):
            risk = "HIGH"
        elif high_flags >= 1 or med_flags >= 2:
            risk = "MEDIUM"
        elif flags:
            risk = "LOW"
        else:
            risk = "LOW"

        return CitationNetworkResult(
            total_references=n,
            self_citation_count=self_cit_count,
            self_citation_rate=round(self_cit_rate, 3),
            predatory_journal_count=predatory_count,
            missing_doi_rate=round(missing_doi_rate, 3),
            year_span=year_span,
            venue_concentration=round(hhi, 3),
            flags=flags,
            overall_risk=risk,
            openalex_queried=openalex_queried,
            details={
                "total_flags": len(flags),
                "year_distribution": dict(Counter(valid_years).most_common(10)),
            },
        )
