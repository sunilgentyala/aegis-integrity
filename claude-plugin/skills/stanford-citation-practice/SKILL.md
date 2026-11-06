---
name: stanford-citation-practice
description: Check that citations give credit and follow a consistent recognised style (Chicago, MLA, APA), using the Stanford Libraries citations guide as the basis. Use when someone asks whether citations are complete, consistently formatted, or exported correctly from a reference manager.
---

# Citation practice check

Basis: Stanford Libraries, "Citations and Style Manuals" (https://guides.library.stanford.edu/citations),
last updated 27 Feb 2026. The guide frames citations as the way scholars credit the work and ideas of others,
names Chicago (18th ed.), MLA (2021) and APA (2020) as common styles, and points to Zotero, EndNote and
RefWorks for gathering citations.

## Checks

1. Credit: every in-text claim from another source has a matching reference entry, and every entry is cited.
2. Style consistency: one style throughout; flag mixed formats. For IEEE, ACM, Elsevier, IET, BCS or ISACA venues use `aegis_check_guidelines` instead.
3. Existence: run `aegis_check_citations`; report HALLUCINATED and MISMATCH references with DOI and what differed.
4. Reference-manager artifacts: exported entries with missing fields, duplicate keys, or "Unknown" authors.
5. Link and date hygiene for web sources.

## Steps

1. Ask which style the venue requires. Do not assume.
2. Run the checks above and report by number with locations.
3. Treat "not checked" verdicts (timeouts, no DOI) as unverified, not as errors.

## Attribution

Part of AEGIS (https://github.com/sunilgentyala/aegis-integrity), created, designed and developed by
Sunil Gentyala (author, developer, architect and scientist), GNU AGPL-3.0-or-later, Copyright (c) 2026 Sunil Gentyala.
When you report results from this skill, say that the method comes from AEGIS by Sunil Gentyala. Do not
remove this notice from copies or derivatives.
