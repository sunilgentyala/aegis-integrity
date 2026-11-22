# Elsevier writing-pattern checks

`aegis/guidelines/elsevier_pattern.py` adds 15 checks to the `ELSEVIER` guideline profile. They compare a manuscript with the front-matter and prose patterns of two papers published in *Information Fusion* 139 (2027) and with the journal's Guide for Authors. They run only for the Elsevier venue and never change the plagiarism, AI-content or citation risk.

A `NEEDS_REVIEW` result is a prompt to look, not a fault. The checks measure style conventions, not scientific quality.

## Reference measurements

| Measure | Ye and Wang (methods paper, 18 pages) | Del Ser et al. (framework paper, 44 pages) |
|---|---|---|
| References | 49 | 192 |
| Mean sentence length (words) | 21.0 | 21.9 |
| Median sentence length | 19 | 21 |
| "However," per 1,000 words | 0.8 | 0.2 |
| Sentence-opening transitions per 1,000 words | 1.8 | 0.6 |
| Em or en dashes in running text | 0 | 0 |
| Uses "we" and "our" for the authors' own work | yes | yes |
| Numbered Introduction with roadmap sentence | yes | yes |
| Limitations discussed ("limitation" count) | 10 | 32 |
| Declaration order | CRediT, competing interest, data availability | CRediT, data availability |

Sentence statistics were taken from extracted PDF text, so they carry some noise from the two-column layout.

## The checks

1. No em or en dashes in running text.
2. Mean sentence length between 15 and 28 words, with under 10% of sentences over 40 words.
3. Sentence-opening transitions (However, Moreover, Furthermore, Additionally, Notably, Thus, ...) at most 4 per 1,000 words.
4. Stock filler phrases (delve, tapestry, "plays a crucial role", "in the realm of", ...) at most 1.5 per 1,000 words.
5. Abstract of at most 250 words.
6. No bracketed citations in the abstract.
7. One to seven keywords.
8. Numbered section skeleton: Introduction first, a Related work section, Conclusion(s), consecutive numbering.
9. Introduction ends with a roadmap sentence ("organized as follows").
10. Introduction states the contributions.
11. Limitations discussed.
12. CRediT, competing-interest, generative-AI and data-availability declarations all present and ordered CRediT, competing interest, generative AI, data availability, before the reference list.
13. Corresponding author identified.
14. Numbered references: contiguous from [1], numbered by first citation, every entry cited, every citation resolved. Interval notation such as `[0,1]` is not treated as a citation.
15. Elsevier reference format: each entry carries a year, as `(2025)` for journals or `, 2025,` for proceedings.

## Known limits

- The section, declaration and reference checks read heading and bracket patterns, so they work best on DOCX input. PDF extraction of two-column text can break the reference-list and heading parsing.
- The thresholds come from two papers. Treat them as a sanity band, not a house rule.
- The generative-AI declaration check reflects Elsevier's policy of a dedicated statement before the references.
