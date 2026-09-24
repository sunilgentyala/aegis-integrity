---
name: integrity-check
description: Check a paper, thesis, essay or manuscript (PDF, DOCX, TEX, TXT) for copied or paraphrased text, AI-written passages, fabricated or mismatched references, and writing-style shifts, then explain the results in plain language. Use when someone asks whether a document is plagiarised, AI-generated, has fake citations, or is "safe to submit".
---

# Integrity check with AEGIS

AEGIS runs on the user's own computer. Only reference metadata (titles,
authors, DOIs) is sent to Crossref, and only when citation checking is on.

## Steps

1. Get the **absolute path** to the document. If the user gave a relative
   path or a file name, resolve it first; the tools reject missing files.
2. If this is the first AEGIS call in the session, or a previous result said
   a check was "unavailable" or "skipped", call `aegis_status` and tell the
   user about anything not ready, with the fix command it gives.
3. Call `aegis_analyze_paper` with the path.
   - The first full run can take several minutes (AI models download once).
     Tell the user this before calling. If they want speed over coverage,
     pass `skip_ai_detection=true`.
   - If the user wants nothing sent over the internet, pass
     `skip_citations=true` and say that references were not verified.
   - For their own earlier papers (self-plagiarism), pass `prior_works_dir`.
4. Report back in this order:
   - **Overall risk** (LOW / MEDIUM / HIGH / CRITICAL) and one sentence on
     what it means.
   - **What to look at**: each flag rewritten in plain language, most
     serious first. For references, list the ones marked HALLUCINATED or
     MISMATCH with their DOI and what differed.
   - **What was not checked**, and why (for example "copied-text check
     skipped: no comparison library"). Never let a skipped check read as a
     clean result.
   - The path of the HTML report.

## How to talk about results

- A flag is a reason to look closer, **not proof of misconduct**. Say so once,
  clearly. Never tell the user a person cheated or used AI.
- AI-writing scores are probabilistic. AEGIS calibrates them for non-native
  English writers, but no detector is reliable enough to act on alone.
- "Copied text" only covers documents in the local comparison library. If
  the library is empty or small, say that a clean result does not mean the
  text is original. Offer `aegis_index_add` to add sources.
- "Not checked" reference verdicts (timeouts, no DOI, registered outside
  Crossref) are not problems with the paper.
- Year differences of one between a citation and Crossref are usually
  online-first vs. print dates; AEGIS already accepts either.
