"""
Per-venue guideline compliance checking -- AEGIS v3.0 Novel Feature.

Runs the math-formula and grammar/language findings (see
aegis.detectors.math_formula and aegis.detectors.grammar) through a
distinct, separately-reported compliance pass for each of five publishing
bodies -- IEEE, ACM, BCS, IET, ISACA -- rather than one generic merged
check. Each venue has its own documented conventions (see profiles.py for
sourcing); running them separately means a document that is fine by ACM's
conventions but violates an IEEE-specific one (or vice versa) is visible
per-venue instead of being averaged away.

This is advisory, not adjudicative: results are PASS / NEEDS_REVIEW /
NOT_ENOUGH_DATA, never "FAIL" or "REJECTED" -- these are style
conventions, not academic-integrity findings, and AEGIS does not claim to
be the venue's editorial desk.
"""

from aegis.guidelines.profiles import (
    GuidelineProfile, GUIDELINE_PROFILES, DEFAULT_GUIDELINE_VENUES, resolve_guideline_profiles,
)
from aegis.guidelines.checker import GuidelineComplianceChecker, GuidelineComplianceResult, ComplianceCheck

__all__ = [
    "GuidelineProfile", "GUIDELINE_PROFILES", "DEFAULT_GUIDELINE_VENUES",
    "resolve_guideline_profiles", "GuidelineComplianceChecker",
    "GuidelineComplianceResult", "ComplianceCheck",
]
