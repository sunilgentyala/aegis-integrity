"""
Target Publisher Registry -- shared reference data for venue-scoped checks.

AEGIS cannot query IEEE Xplore, ACM Digital Library, or ScienceDirect full
text directly: that content only lives behind Crossref's Similarity Check
database, which is restricted to paying member organizations, not
individual tools (see https://www.crossref.org/services/similarity-check/).
Scopus and IEEE Xplore's public APIs are metadata/abstract-only even with a
key. What IS free and public is Crossref's own metadata index, which every
DOI-registering publisher -- including all six venues below -- feeds
regardless of whether that publisher offers its own API.

So "verify against IEEE/ACM/Elsevier/IET/IETE/BCS" is implemented here as
two things Crossref metadata actually supports:
  1. Classify an already-resolved citation's DOI/publisher/container-title
     against these six venues, to catch a claimed venue ("Published in IEEE
     Transactions...") that doesn't match what the DOI actually resolves to.
  2. Scope a Crossref bibliographic search to a publisher's member id (or,
     for imprints that don't hold their own Crossref membership, to a
     known DOI prefix + container-title pattern) to find near-duplicate
     titles already published under that venue.

IEEE (member 263), ACM (member 320), Elsevier (member 78), and IET
(member 265) are Crossref members in their own right. IETE journals
(IETE Journal of Research, IETE Technical Review) are published by
Informa UK Limited / Taylor & Francis under DOI prefix 10.1080, and BCS's
flagship titles (The Computer Journal, ITNOW) are published by Oxford
University Press under prefix 10.1093 -- neither IETE nor BCS holds an
independent Crossref membership, so those two are matched by DOI prefix
plus container-title keywords instead of a member id. Verified against
the live Crossref /members API in August 2026; publishers occasionally
change registration agencies, so treat CROSSREF_MEMBER_ID as best-effort,
not a guarantee.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PublisherProfile:
    key: str                              # short id, e.g. "IEEE"
    display_name: str
    crossref_member_id: Optional[str]     # None if not its own Crossref member
    doi_prefixes: tuple[str, ...]         # known DOI prefixes for this venue
    container_keywords: tuple[str, ...]   # substrings matched against container-title
    claim_keywords: tuple[str, ...]       # substrings that indicate a raw citation
                                           # is *claiming* publication by this venue


TARGET_PUBLISHERS: dict[str, PublisherProfile] = {
    "IEEE": PublisherProfile(
        key="IEEE",
        display_name="IEEE",
        crossref_member_id="263",
        doi_prefixes=("10.1109", "10.30941", "10.21629", "10.47962", "10.23919"),
        container_keywords=("ieee",),
        claim_keywords=("ieee",),
    ),
    "ACM": PublisherProfile(
        key="ACM",
        display_name="ACM (Association for Computing Machinery)",
        crossref_member_id="320",
        doi_prefixes=("10.1145", "10.14778"),
        container_keywords=("acm", "association for computing machinery"),
        claim_keywords=("acm", "association for computing machinery"),
    ),
    "Elsevier": PublisherProfile(
        key="Elsevier",
        display_name="Elsevier",
        crossref_member_id="78",
        doi_prefixes=("10.1016",),
        container_keywords=("elsevier",),
        claim_keywords=("elsevier", "sciencedirect"),
    ),
    "IET": PublisherProfile(
        key="IET",
        display_name="IET (Institution of Engineering and Technology)",
        crossref_member_id="265",
        doi_prefixes=("10.1049",),
        container_keywords=("iet", "institution of engineering and technology"),
        claim_keywords=("iet", "institution of engineering and technology"),
    ),
    "IETE": PublisherProfile(
        key="IETE",
        display_name="IETE (Institution of Electronics and Telecommunication Engineers)",
        crossref_member_id=None,  # published via Informa UK Ltd / Taylor & Francis
        doi_prefixes=("10.1080",),
        container_keywords=("iete",),
        claim_keywords=("iete",),
    ),
    "BCS": PublisherProfile(
        key="BCS",
        display_name="BCS (The Chartered Institute for IT)",
        crossref_member_id=None,  # flagship journals published via Oxford University Press
        doi_prefixes=("10.1093",),
        container_keywords=("computer journal", "computer bulletin", "itnow"),
        claim_keywords=("bcs", "british computer society", "chartered institute for it"),
    ),
}

DEFAULT_TARGET_PUBLISHERS: tuple[str, ...] = (
    "IEEE", "ACM", "Elsevier", "IET", "IETE", "BCS",
)


def _keyword_present(text_lower: str, keyword: str) -> bool:
    """
    Whole-word/phrase match, not bare substring containment.

    Several of the venue keywords are short and generic ("iet", "iete",
    "acm", "bcs"), so a plain `keyword in text` check false-matches inside
    unrelated words -- "a quiet cooling system" contains "iet", "the noise
    was quieted" contains "iete", "pacman-style scheduling" contains "acm".
    Each of those would previously produce a spurious VENUE_MISMATCH flag
    (conference/venue attribution) or a spurious prior-publication
    classification, with no actual claim of the venue anywhere in the text.
    Matching only when the keyword isn't glued to a letter/digit on either
    side keeps single-word abbreviations like "IET" or "ACM" working while
    ruling out these collisions.
    """
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.strip()) + r"(?![a-z0-9])"
    return re.search(pattern, text_lower) is not None


def classify_publisher(
    doi: Optional[str], container_title: Optional[str] = None,
) -> Optional[str]:
    """
    Given a resolved DOI (and optionally its container-title), return the
    matching target-publisher key ("IEEE", "ACM", ...) or None if it does
    not belong to any of the six tracked venues.

    Prefix match alone is sufficient for the four independent Crossref
    members (IEEE/ACM/Elsevier/IET); IETE and BCS share a DOI prefix with
    thousands of unrelated Informa/OUP titles, so those two additionally
    require a container-title keyword hit to avoid false positives (e.g.
    classifying an unrelated Taylor & Francis journal as IETE).
    """
    if not doi:
        return None
    prefix = doi.split("/")[0] if "/" in doi else doi
    container_lower = (container_title or "").lower()

    for profile in TARGET_PUBLISHERS.values():
        if prefix not in profile.doi_prefixes:
            continue
        if profile.crossref_member_id is not None:
            return profile.key
        if container_lower and any(
            _keyword_present(container_lower, kw) for kw in profile.container_keywords
        ):
            return profile.key
    return None


def claimed_publisher(raw_citation_text: str) -> Optional[str]:
    """
    Best-effort guess at which of the six target venues a raw reference
    string is claiming to be published by, based on venue-name keywords in
    the citation text itself (e.g. "IEEE Trans. on ...", "Proc. ACM ...").
    Returns None if no target-venue keyword is found -- most references
    won't claim any of these six venues, and that's not itself a signal.

    Returns only the first keyword match (in TARGET_PUBLISHERS order) --
    for a reference that names more than one venue (a jointly-sponsored
    conference like "IEEE/ACM ... Conference"), use
    claimed_publishers_all() instead so a mismatch check isn't fooled into
    comparing against only one of the names actually present.
    """
    text_lower = (raw_citation_text or "").lower()
    for profile in TARGET_PUBLISHERS.values():
        if any(_keyword_present(text_lower, kw) for kw in profile.claim_keywords):
            return profile.key
    return None


def claimed_publishers_all(raw_citation_text: str) -> set[str]:
    """
    Every target-venue keyword found in a raw reference string, not just
    the first. A jointly-sponsored venue is routinely named as both
    co-sponsors ("Proceedings of the IEEE/ACM 12th International
    Conference on ...") and its DOI can legitimately resolve to either
    co-sponsor's Crossref member -- checking against only the first-listed
    name (what claimed_publisher() returns) produces a false
    venue-mismatch flag when the DOI resolves to the second-listed one.
    """
    text_lower = (raw_citation_text or "").lower()
    return {
        profile.key
        for profile in TARGET_PUBLISHERS.values()
        if any(_keyword_present(text_lower, kw) for kw in profile.claim_keywords)
    }


def resolve_target_publishers(
    requested: Optional[list[str]],
) -> list[PublisherProfile]:
    """Validate and resolve a list of publisher keys (case-insensitive) to
    their PublisherProfile, defaulting to all six when none are given."""
    keys = requested or list(DEFAULT_TARGET_PUBLISHERS)
    profiles = []
    for k in keys:
        profile = TARGET_PUBLISHERS.get(k) or TARGET_PUBLISHERS.get(k.upper())
        if profile:
            profiles.append(profile)
    return profiles
