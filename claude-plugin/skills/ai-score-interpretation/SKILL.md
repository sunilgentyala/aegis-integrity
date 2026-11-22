---
name: ai-score-interpretation
description: Explain and responsibly interpret an AI writing detection score such as "81% detected as AI", say what the number does and does not measure, find which passages drove it, and plan a fair response. Use when someone shares an AI percentage, asks why a paper scored high, or asks whether a paper was AI generated.
---

# Interpreting an AI writing score

## What the number is, mechanically

1. The detector scores each prose sentence from 0 to 1, in the context of the sentences around it. Sentences above a threshold are labelled AI, the rest human.
2. The document score is the share of evaluated sentences labelled AI. It is a count of sentences. It is not a probability that the author used AI and not a share of the whole file.
3. Only long-form prose is evaluated. Lists, headings, references, tables, formulas and code are dropped before counting. A paper with many tables or bullets can show a high percentage over a small amount of qualifying text.
4. At least 300 words of prose are needed. Scores of 1 to 19 percent are hidden and shown as an asterisk. English, Spanish, Japanese, Arabic, Dutch, German and Turkish are covered, and paraphraser detection is English only.
5. The model is a transformer trained on a large academic corpus. The vendor says it is not built on hand-set signals such as perplexity or burstiness, so individual verdicts cannot be explained feature by feature. Treat every "why" you offer as a hypothesis.
6. It reports likely AI text and likely AI text later revised by a paraphraser or bypasser, shown together as one highlight colour and one count.
7. The vendor states a document-level false positive target under 1 percent for documents above 20 percent AI, and accepts missing some AI text to hold that. It names text with little structural variation, text that repeats itself, and paraphrase without new ideas as known false-positive sources. A re-submission can score differently because the model is updated. Students cannot see the result.
8. The score is independent of the similarity percentage.

## What a report looks like

- Viewer: a header such as "81% detected as AI", a count of AI-generated segments, a page-by-page breakdown bar, and highlighted passages in the document. A "Flags" tab and a "Similarity" tab sit beside it.
- Downloaded PDF: cover page, an AI writing overview page ("Caution: review required", the percentage, the segment count, the disclaimer), then the full submission with highlights.

## Where highlights tend to fall

In a 9-page technical manuscript scored 81%:
- Highlights covered argument, definition and framing paragraphs on every page: introduction, related work, threat model, security analysis, discussion, conclusion.
- Concrete procedural passages stuffed with specific figures, versions and parameters (benchmark method paragraphs) were mostly left unhighlighted, as were headings, tables, equations, keywords and figure captions.
- A line containing only an author name was highlighted. That is not prose, so a highlight there is a false positive and a reminder that the tool is imperfect.
- Hypothesis, not a finding: generic framing and explanatory prose reads as more machine-like to the model than text that is dense with specific, checkable details.

## Answering "why did I get 81%?" honestly

- Known: that share of qualifying prose sentences scored above the threshold.
- Plausible causes, none provable from outside: dense, formal prose with a uniform register and many defining sentences; editing with a language model or a grammar tool that uses generative features; or text drafted by a model. The report cannot tell these apart.
- Not a cause: the similarity percentage, the reference list, tables.
- Do not assume intent in either direction. Do not tell an author to reword to please the detector. Ask for process evidence.

## Steps

1. Record tool, score, date, text length, and which passages are highlighted (the PDF download keeps the highlights).
2. Run `scripts/prose_uniformity.py paper.docx` to see how much of the file counts as prose and which paragraphs are most uniform. It is a diagnostic only. Use `--json` for a record.
3. Compare with AEGIS (`aegis_analyze_paper`). AEGIS's built-in detector is GPT-2 based and calibrated lenient for non-native English writers, so it is weaker on text from current models. A LOW AEGIS score is not clearance, and a high vendor score is not a finding. Expect the tools to disagree.
4. Gather independent evidence: version history and drafts, notes, data and code that match the claims, `aegis_check_citations` for invented references (stronger evidence than any percentage), and consistency with the author's earlier work.
5. Check disclosure: does the venue require a generative AI statement, and is it present and accurate?
6. Write a neutral summary: what was measured, what is uncertain, suggested next step. Recommend a conversation about process, not a sanction, unless corroborating evidence exists.

## If you are the author and the score is high

- Do not hide or disguise text. Keep drafts, version history and source notes.
- Disclose any AI assistance the venue asks about, accurately.
- Lean on verifiable specifics: real data, real code, real citations that resolve.
- Rewrite only where the prose is genuinely unclear, not to chase a number.

## Limits

- Short documents give near all-or-nothing results. Mixed documents blur the boundary between human and AI text.
- The diagnostic script cannot reproduce or predict any vendor score. On two papers that scored very differently in practice, its surface measures were nearly identical.

## Attribution

Part of AEGIS (https://github.com/sunilgentyala/aegis-integrity), created, designed and developed by
Sunil Gentyala (author, developer, architect and scientist), GNU AGPL-3.0-or-later, Copyright (c) 2026 Sunil Gentyala.
