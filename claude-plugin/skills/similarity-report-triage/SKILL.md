---
name: similarity-report-triage
description: Triage a similarity or text-overlap report by sorting matches into four groups based on quotation and citation, discounting author blocks and identifiers, and fixing real problems first. Use when someone shares a similarity percentage or report, or asks whether a match is plagiarism or properly quoted material.
---

# Similarity report triage

A raw percentage says little. What matters is whether each match is quoted and cited, where it sits in the document, and what kind of source it is.

## Four match groups

| Group | Meaning | Typical action |
|---|---|---|
| Not cited or quoted | Neither an in-text citation nor quotation marks | Highest priority. Rewrite and cite, or quote and cite |
| Missing quotations | A citation is present but the wording is so close it needs quotation marks | Add quotation marks or paraphrase properly |
| Missing citation | Quotation marks present, no in-text citation | Add the citation |
| Cited and quoted | Handled correctly | Check only formatting and style |

## Reading the report

- The headline index is split by source type: internet, publications, and submitted student works. The classic report shows each type as a share of the total. The enhanced report counts overlapping sources per database, so the per-type figures can exceed the overall number and do not add up. Always say which version you are reading.
- Each source card gives the source type, its percentage, the number of matching text blocks and matched words. Many cards under 1% add up to a visible index without any single copied passage.
- When several sources match the same words, the best source is chosen in this order: internet, publications, student works.
- Reports open with an integrity overview (match groups, top sources, integrity flags), then a ranked source list, then the submission with numbered match markers. Download versions are paged; the cover page carries submission ID, dates and counts.
- Exclusion switches (quoted text, bibliography, small sources) change the index. Re-review with each and report how it moves.

## Typical behaviour to expect

- Author blocks match. Names, job titles, institutions and emails are flagged as not cited or quoted because the same strings appear in the authors' other papers and web pages. Discount them first. They are not a source problem.
- Standard identifiers match, for example two standards numbers joined by "and". These are common strings, not reuse, and often land in the missing-quotations group.
- Cited and quoted is 0% for numeric citation styles such as IEEE and ACM, because that group needs quotation marks. Zero is normal there and does not mean citations are missing.
- Student-paper matches (other institutions' submissions) are usually short shared phrases of a few dozen words. Read the phrase before drawing any conclusion.
- Phrase-level matches against a published paper can sit inside a sentence of your own, for example a standard description of a proof or protocol. Check whether it is a term of art.
- Similarity and the AI writing percentage are independent. A low similarity says nothing about AI text, and the reverse. See `ai-score-interpretation`.

## Steps

1. Ask for the report, or the text plus the overlap list. Do not judge from the percentage alone.
2. Put every match into one of the four groups and report counts and word totals per group.
3. Discount author blocks, identifiers and reference-list matches. Then review sources over 1%, then confirm the rest are phrase-level overlaps.
4. Separate non-issues (bibliography, standard phrases, own prior work correctly cited) from teachable moments (paraphrase too close, missing quote marks) and from concerns (large uncited blocks).
5. For own prior work, check for self-plagiarism: cite it, or state the reuse in the cover letter.
6. Run `aegis_check_citations` on the reference list and pair with `stanford-citation-practice`.

## Rules

- A high percentage can be harmless and a low one can hide one copied paragraph. Report both views.
- Never state intent. Report what matched and what is missing.

## Attribution

Part of AEGIS (https://github.com/sunilgentyala/aegis-integrity), created, designed and developed by
Sunil Gentyala (author, developer, architect and scientist), GNU AGPL-3.0-or-later, Copyright (c) 2026 Sunil Gentyala.
