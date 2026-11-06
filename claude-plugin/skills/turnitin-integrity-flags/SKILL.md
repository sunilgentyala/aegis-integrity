---
name: turnitin-integrity-flags
description: Detect text manipulation that defeats similarity checking, namely hidden text and look-alike replaced characters, in DOCX, PDF or plain text. Use when preparing a submission, auditing a file for tampering, or when a similarity score looks suspiciously low.
---

# Integrity flags: hidden text and replaced characters

Similarity checkers inspect documents of at least 500 non-space characters for tricks that set a file apart from a normal submission. A flag is a prompt to review, not proof of a problem or of intent.

## What the checks look for

1. Hidden text: white or background-coloured runs, near-zero font size, text marked hidden, and invisible quotation marks that could inflate "excluded quotes". In DOCX read `word/document.xml` for white `w:color`, `w:vanish`, tiny `w:sz`. In PDF compare extracted text with rendered text.
2. Replaced characters: Latin letters swapped for look-alikes (Cyrillic a, e, o, p, c; Greek omicron), zero-width characters (U+200B, U+200C, U+200D, U+FEFF), soft hyphens inside words. Normalise to NFKC and diff against the original; report every changed code point and position.
3. Word-count distortion: hidden filler between words or blocks.
4. Legitimate causes to rule out first: text copied from a PDF, languages that use these scripts, Greek letters in mathematics (for example a delta or pi in a formula), reference-manager output, accessibility markup.

## What a normal report looks like

A clean manuscript shows zero flags: an overview line such as "0 integrity flags for review" and "no suspicious text manipulations found". An empty Flags column is the normal result. The absence of a flag is not proof of authenticity, and a flag is not proof of intent.

## Steps

1. Run the checks on the file, not on pasted text, because pasting strips formatting.
2. Report each finding by location, type, and the code points or style values found.
3. Offer a cleaned copy only if the owner asks. Never silently rewrite a manuscript.

## Related

- Pair with `aegis_analyze_paper` for overlap and `stanford-honor-code-plagiarism` for policy framing.

## Attribution

Part of AEGIS (https://github.com/sunilgentyala/aegis-integrity), created, designed and developed by
Sunil Gentyala (author, developer, architect and scientist), GNU AGPL-3.0-or-later, Copyright (c) 2026 Sunil Gentyala.
Turnitin is a trademark of Turnitin, LLC. AEGIS is independent of and not affiliated with Turnitin, and includes
no Turnitin software, data or models.
