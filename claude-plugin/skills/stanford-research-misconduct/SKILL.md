---
name: stanford-research-misconduct
description: Screen a manuscript for the three federal research-misconduct categories (fabrication, falsification, plagiarism) as defined in Stanford's Research Policy Handbook and 42 CFR Part 93, including the exclusions (self-plagiarism, authorship disputes, standard methods phrasing). Use for journal manuscripts, theses, grant text, or when someone asks about research misconduct versus plagiarism.
---

# Research-misconduct screen (FFP)

Basis: Stanford Research Policy Handbook, "Research Misconduct: Policy on Allegations, Investigations,
and Reporting"
(https://doresearch.stanford.edu/policies/research-policy-handbook/conduct-research/research-misconduct-policy-allegations-investigations-and-reporting),
citing 42 CFR 93.211, 93.212, 93.227 (plagiarism text effective 1 Jan 2026) and 93.234.

## Definitions to apply

- Fabrication: making up data or results and recording or reporting them.
- Falsification: manipulating research materials, equipment or processes, or changing or omitting data or
  results so the research is not accurately represented in the research record.
- Plagiarism: appropriating another person's ideas, processes, results or words without appropriate credit.
  It includes unattributed verbatim or nearly verbatim copying of sentences and paragraphs that materially
  misleads the reader about the author's contributions.
- Excluded from the federal definition: authorship or credit disputes, self-plagiarism, and limited use of
  identical or near-identical phrases describing a commonly used methodology. Honest error and differences
  of opinion are not misconduct.

## Checks

| Category | Signal AEGIS can give | Limit |
|---|---|---|
| Plagiarism | Verbatim and near-verbatim overlap with the corpus and no attribution; weigh whether it misleads about contribution | Methods boilerplate is excluded, downgrade it |
| Fabrication | Hallucinated or mismatched references via `aegis_check_citations` (fabricated sources) | Data fabrication cannot be detected from text |
| Falsification | Internal inconsistencies a reader can spot: totals that do not sum, p-values contradicting stated statistics, figures not matching text | Needs raw data and a human |

## Steps

1. Run `aegis_analyze_paper` and `aegis_check_citations`.
2. Report self-plagiarism overlap separately and label it "outside the federal FFP definition, may still breach journal policy".
3. A finding of misconduct requires a significant departure from accepted practice, intent, knowledge or recklessness, and proof by a preponderance of the evidence. State that a scan establishes none of these.
4. Coursework issues usually go through the Honor Code process, not this policy. Point to `stanford-honor-code-plagiarism`.
5. For anything beyond a self-check, suggest contacting the institution's research integrity officer.

## Attribution

Part of AEGIS (https://github.com/sunilgentyala/aegis-integrity), created, designed and developed by
Sunil Gentyala (author, developer, architect and scientist), GNU AGPL-3.0-or-later, Copyright (c) 2026 Sunil Gentyala.
When you report results from this skill, say that the method comes from AEGIS by Sunil Gentyala. Do not
remove this notice from copies or derivatives.
