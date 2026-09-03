"""
Guideline profiles for IEEE, ACM, BCS, IET, and ISACA.

Every field below is sourced from that body's own (or its publishing
partner's) current author-facing documentation, listed in `source_url`.
Where the source material did not explicitly state a convention (e.g. The
Computer Journal's author instructions do not say outright "use British
English"), the field is set to the best-supported inference and flagged
via `*_confidence = "inferred"` rather than presented as an explicit
rule -- see GuidelineComplianceChecker, which reports inferred rules as
NOT_ENOUGH_DATA / lower-confidence NEEDS_REVIEW rather than a firm
violation.

Sources consulted (August 2026):
  IEEE     -- IEEE Editorial Style Manual for Authors (2024), updated
              29 July 2024. journals.ieeeauthorcenter.ieee.org
  ACM      -- ACM formatting/reference guidance (Chicago Manual of Style base,
              numeric citation, ACM Primary Article Template).
              acm.org/publications/authors
  BCS      -- The Computer Journal (BCS's flagship research journal,
              published by Oxford University Press) General Instructions /
              Manuscript Preparation. academic.oup.com/comjnl/pages
  IET      -- IET Research Journals Author Guide.
              digital-library.theiet.org/journals
  ISACA    -- ISACA Journal Article Submission Guidelines.
              isaca.org/resources/isaca-journal/submit-an-article

Sources consulted (September 2026):
  ELSEVIER -- Elsevier "Your Paper Your Way" / Guide for Authors (spelling
              consistency rule), CRediT author statement policy
              (elsevier.com/researcher/author/policies-and-guidelines/
              credit-author-statement), Highlights guide
              (elsevier.com/researcher/author/tools-and-resources/highlights),
              and Declaration of Competing Interest / Data Availability
              Statement policy pages. Structural conventions (CRediT
              placement, numbered-reference style, equation numbering)
              additionally cross-checked against a real published
              ScienceDirect article (Biomedical Signal Processing and
              Control 115 (2026) 109428, doi:10.1016/j.bspc.2025.109428) --
              that sample paper mixes British and American spelling
              throughout (e.g. "regularisation" alongside
              "characterizations"), which is a concrete illustration of
              the exact inconsistency Elsevier's own guidance says not to
              do, not a counterexample to the rule.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class GuidelineProfile:
    key: str
    display_name: str
    source_name: str
    source_url: str

    spelling_variant: str                 # "US" | "UK" | "EITHER"
    spelling_variant_confidence: str      # "stated" | "inferred"

    allow_contractions: bool
    require_oxford_comma: bool

    require_third_person: bool
    disallow_first_person_singular: bool  # "I" / direct address ("you")

    equation_ref_style: Optional[str]     # e.g. "bare-parens" | "number-in-parens" | None
    equation_ref_note: str

    citation_style: str                   # "numeric-bracket" | "endnote" | "unspecified"

    word_count_range: Optional[tuple[int, int]]   # (min, max) target, if stated
    discourage_bulleted_lists: bool

    notes: tuple[str, ...] = field(default_factory=tuple)

    # Structural-element requirements (Elsevier-specific as of Sept 2026;
    # default False/None for the other four venues, whose sourced author
    # guidance does not mandate these specific sections/files).
    require_credit_statement: bool = False
    require_conflict_of_interest_statement: bool = False
    require_data_availability_statement: bool = False
    highlights_max_bullets: Optional[int] = None
    highlights_max_chars: Optional[int] = None


GUIDELINE_PROFILES: dict[str, GuidelineProfile] = {
    "IEEE": GuidelineProfile(
        key="IEEE",
        display_name="IEEE",
        source_name="IEEE Editorial Style Manual for Authors (2024)",
        source_url="https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/"
                    "sites/7/IEEE-Editorial-Style-Manual-for-Authors.pdf",
        spelling_variant="US", spelling_variant_confidence="stated",
        allow_contractions=False, require_oxford_comma=True,
        require_third_person=False, disallow_first_person_singular=False,
        equation_ref_style="number-in-parens",
        equation_ref_note='Use the word "Equation" only at the start of a '
                           'sentence; otherwise cite the bare number, e.g. "in (1)".',
        citation_style="numeric-bracket",
        word_count_range=None, discourage_bulleted_lists=False,
        notes=(
            'Spelling: "IEEE Transactions use the first spelling of a word as '
            'given in the main entry of The Merriam-Webster Dictionary"; British '
            "spellings (behaviour, centre, polarisation) are converted to American.",
            'Contractions "such as \'don\'t\' and \'can\'t\' are not used in '
            'technical text," with idiomatic exceptions for "don\'t-care," '
            '"best-case," and "worst-case."',
            "Equation numbering must be consecutive, flush right, with no "
            "repeated or missing numbers.",
            'Series of three or more terms take a comma before the coordinating '
            'conjunction (Oxford/serial comma).',
        ),
    ),
    "ACM": GuidelineProfile(
        key="ACM",
        display_name="ACM (Association for Computing Machinery)",
        source_name="ACM Formatting Guide / Reference Guide",
        source_url="https://www.acm.org/publications/authors/information-for-authors",
        spelling_variant="US", spelling_variant_confidence="inferred",
        allow_contractions=False, require_oxford_comma=True,
        require_third_person=False, disallow_first_person_singular=False,
        equation_ref_style="number-in-parens",
        equation_ref_note='Display equations are numbered with the number in '
                           'parentheses on the right margin; referenced as "(n)" '
                           'or "Eq. (n)".',
        citation_style="numeric-bracket",
        word_count_range=None, discourage_bulleted_lists=False,
        notes=(
            "ACM uses The Chicago Manual of Style as its base text-formatting "
            "reference, which specifies American spelling and the serial comma.",
            "References are listed numerically in citation order; in-text "
            'citations are bracketed numerals, e.g. "[1]".',
            "ACM's stated preference is full author names in references, not "
            "initials.",
        ),
    ),
    "BCS": GuidelineProfile(
        key="BCS",
        display_name="BCS (The Chartered Institute for IT) -- The Computer Journal",
        source_name="The Computer Journal: General Instructions / Manuscript "
                     "Preparation (Oxford University Press)",
        source_url="https://academic.oup.com/comjnl/pages/General_Instructions",
        spelling_variant="UK", spelling_variant_confidence="inferred",
        allow_contractions=True, require_oxford_comma=False,
        require_third_person=False, disallow_first_person_singular=False,
        equation_ref_style=None,
        equation_ref_note="No explicit equation citation-phrasing convention is "
                           "published; the journal's LaTeX guidance covers only "
                           'typesetting ("use $ for mathematics where possible").',
        citation_style="numeric-bracket",
        word_count_range=None, discourage_bulleted_lists=False,
        notes=(
            "The Computer Journal is published by Oxford University Press under "
            'the "Oxford SCIMED" house style; OUP journals default to British '
            "English spelling, though the author instructions do not restate this "
            "explicitly for every submission -- treated here as inferred, not stated.",
            'References use a numbering style: "reference number 1 being [the] '
            'first reference mentioned in the text."',
            "No contraction or serial-comma rule is published; not enforced here.",
        ),
    ),
    "IET": GuidelineProfile(
        key="IET",
        display_name="IET (Institution of Engineering and Technology)",
        source_name="IET Research Journals Author Guide",
        source_url="https://digital-library.theiet.org/journals/cje/author-guide",
        spelling_variant="UK", spelling_variant_confidence="inferred",
        allow_contractions=True, require_oxford_comma=False,
        require_third_person=False, disallow_first_person_singular=False,
        equation_ref_style="bare-parens",
        equation_ref_note='"Equations should be referred to using round '
                           'brackets, e.g. (1)" -- bare-number references are '
                           'the IET convention, not "Eq. (1)".',
        citation_style="numeric-bracket",
        word_count_range=None, discourage_bulleted_lists=False,
        notes=(
            "IET is a UK chartered institution; British English spelling is the "
            "house convention, though not restated per-submission in the author "
            "guide -- treated here as inferred, not stated.",
            '"Exponential expressions should be written using superscript '
            'notation (e.g., 5x10³ not 5E03)." A multiplication sign should '
            "be used, not a dot.",
            "Citations should be in numerical order throughout the text; an "
            "average paper references 20-30 works, mostly from the last 5 years.",
        ),
    ),
    "ISACA": GuidelineProfile(
        key="ISACA",
        display_name="ISACA (ISACA Journal)",
        source_name="ISACA Journal Article Submission Guidelines",
        source_url="https://www.isaca.org/resources/isaca-journal/submit-an-article",
        spelling_variant="US", spelling_variant_confidence="stated",
        allow_contractions=True, require_oxford_comma=False,
        require_third_person=True, disallow_first_person_singular=True,
        equation_ref_style=None,
        equation_ref_note="ISACA Journal is a practitioner publication; its "
                           "submission guidelines give no guidance on mathematical "
                           "notation at all.",
        citation_style="endnote",
        word_count_range=(2000, 3000), discourage_bulleted_lists=True,
        notes=(
            '"Write in the third person, avoiding the use of \'I\' or \'you.\'" '
            "-- the only one of these five venues to explicitly mandate this.",
            "Manuscripts are edited for grammar and spelling against The New "
            "York Times Manual of Style and Usage and Merriam-Webster's "
            "Collegiate Dictionary (American English).",
            'Citations use endnotes, not footnotes or numeric brackets; "use '
            'bulleted lists sparingly -- the majority of the article should '
            'consist of paragraphs."',
            "Target length is 2,000-3,000 words; editors may trim for length.",
            "Explicitly prohibits AI-generated or AI-revised submissions -- "
            "unrelated to this tool's own AI-detection module, but worth noting "
            "if AEGIS's AI-content detector also flags the same manuscript.",
        ),
    ),
    "ELSEVIER": GuidelineProfile(
        key="ELSEVIER",
        display_name="Elsevier (ScienceDirect journals)",
        source_name="Elsevier Guide for Authors / CRediT author statement / "
                     "Highlights guide / Declaration of Competing Interest policy",
        source_url="https://www.elsevier.com/researcher/author/policies-and-guidelines/"
                    "credit-author-statement",
        spelling_variant="EITHER", spelling_variant_confidence="stated",
        allow_contractions=True, require_oxford_comma=False,
        require_third_person=False, disallow_first_person_singular=False,
        equation_ref_style="number-in-parens",
        equation_ref_note='Displayed equations are numbered consecutively with the '
                           'number in parentheses at the right margin, referenced as '
                           '"Eq. (n)" or the bare number "(n)".',
        citation_style="varies",
        word_count_range=None, discourage_bulleted_lists=False,
        require_credit_statement=True,
        require_conflict_of_interest_statement=True,
        require_data_availability_statement=True,
        highlights_max_bullets=5,
        highlights_max_chars=85,
        notes=(
            '"American or British usage is accepted, but not a mixture of these" -- '
            "unlike the other four venues here, Elsevier explicitly permits either "
            "variant and only requires internal consistency; there is no single "
            '"correct" target spelling to check against.',
            "A CRediT authorship contribution statement (using the 14-role CRediT "
            "taxonomy: Conceptualization, Methodology, Software, Validation, Formal "
            "analysis, Investigation, Resources, Data Curation, Writing - Original "
            "Draft, Writing - Review & Editing, Visualization, Supervision, Project "
            "administration, Funding acquisition) is required, placed above the "
            "acknowledgments section.",
            "A Declaration of Competing Interest statement is required from every "
            "author, disclosing any financial/personal relationships that could bias "
            "the work (or stating that none exist).",
            "A Data Availability Statement is required by an increasing number of "
            'Elsevier journals (e.g. "Data will be made available on request.").',
            "Highlights: a separate 3-to-5 bullet-point summary, each bullet capped "
            "at 85 characters including spaces, submitted for search-engine "
            "discoverability. Some authors also carry this into the manuscript body "
            "as a \"Highlights\" heading, which is what this check scans for.",
            "Reference/citation style (numbered/Vancouver vs. Harvard/name-date) is "
            "set per journal, not uniformly across Elsevier -- recorded here as "
            '"varies" rather than asserting one convention, so this check reports '
            "NOT_ENOUGH_DATA instead of a false verdict.",
            "Equation numbering/reference convention cross-checked against a real "
            "published ScienceDirect article (Biomedical Signal Processing and "
            "Control 115 (2026) 109428).",
        ),
    ),
}

DEFAULT_GUIDELINE_VENUES: tuple[str, ...] = ("IEEE", "ACM", "BCS", "IET", "ISACA", "ELSEVIER")


def resolve_guideline_profiles(requested: Optional[list[str]]) -> list[GuidelineProfile]:
    """Validate and resolve a list of venue keys (case-insensitive) to their
    GuidelineProfile, defaulting to all five when none are given."""
    keys = requested or list(DEFAULT_GUIDELINE_VENUES)
    profiles = []
    for k in keys:
        profile = GUIDELINE_PROFILES.get(k) or GUIDELINE_PROFILES.get(k.upper())
        if profile:
            profiles.append(profile)
    return profiles
