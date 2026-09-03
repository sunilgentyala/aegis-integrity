"""
AEGIS -- Academic Integrity Engine with Generative-AI Scrutiny

An open-source academic integrity analysis tool that fills critical gaps
in existing plagiarism detection tools:

  1. Citation integrity validation -- DOI resolution + hallucination detection
  2. Language-calibrated AI detection -- bias-aware, ESL-safe scoring
  3. Paragraph-level explainable similarity with source attribution
  4. Stylometric authorship profiling integrated with plagiarism detection
  5. Self-plagiarism cross-corpus comparison (offline, no Turnitin required)
  6. LaTeX source file direct parsing (no PDF conversion artefacts)
  7. Full offline operation -- no commercial API dependency
  8. Structured JSON + HTML explainable reports (not black-box percentages)
  9. Target-publisher verification -- venue-claim and duplicate-submission
     checks scoped to IEEE, ACM, Elsevier, IET, IETE, and BCS via Crossref
 10. Mathematical formula checking -- equation numbering, dangling/orphaned
     reference detection, and notation-convention checks (offline, no ML)
 11. Grammar & language convention checking -- contractions, US/UK spelling
     consistency, subject/verb agreement, usage errors (offline, no ML)
 12. Per-venue publisher guideline compliance -- IEEE, ACM, BCS, IET, ISACA,
     and Elsevier checked SEPARATELY against each body's own sourced style
     guidance, not one generic merged rule set

Authors: Sunil Gentyala, Rakesh Prakash, Akhila Kasturi
License: MIT
"""

__version__ = "3.1.0"
__author__ = "Sunil Gentyala"
