---
name: submission-check
description: Pre-submission check of a manuscript for a specific publisher (IEEE, ACM, Elsevier, IET, BCS or ISACA) - equation numbering and references, grammar and spelling consistency, publisher style rules, and reference verification - producing a fix-list the author can work through. Use when someone is about to submit a paper or asks "is my paper ready for <venue>".
---

# Pre-submission check with AEGIS

## Steps

1. Get the absolute path to the manuscript and the target publisher. If the
   user names a journal or conference, map it to its publisher (for example
   Expert Systems with Applications -> ELSEVIER, an IEEE conference -> IEEE).
   If unclear, ask once.
2. Call `aegis_check_guidelines` with `venues` set to that publisher. It runs
   offline in seconds.
3. Call `aegis_check_citations` to verify every reference against Crossref.
4. If the user also wants plagiarism and AI-writing checks, use the
   `integrity-check` skill afterwards; don't run the slow full analysis
   unless asked.

## Output: a fix-list

Group findings into a numbered checklist the author can act on:

- **Must fix before submitting**: dangling or duplicate equation numbers,
  references AEGIS marked HALLUCINATED or MISMATCH (give the DOI and what
  Crossref returned), guideline checks marked NEEDS_REVIEW.
- **Should fix**: mixed US/UK spelling, inconsistent equation-reference
  phrasing, grammar issues.
- **Check manually**: references AEGIS could not verify (no DOI, timed out,
  registered outside Crossref) - these are not errors, just unverified.

Quote the exact guideline source AEGIS reports for each rule, so the author
can confirm it against the publisher's current guide. Publisher guides
change; AEGIS's rules are a starting point, not the final word.
