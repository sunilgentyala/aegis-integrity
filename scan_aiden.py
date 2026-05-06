"""
AEGIS scan of aiden_elsevier_paper_v2.docx

Detectors active (no torch/SBERT needed):
  - Document parsing         (python-docx)
  - Stylometric analysis     (pure Python -- Burrows' Delta)
  - AI heuristics            (burstiness + stylometric signals; no GPT-2)
  - Citation integrity       (Crossref REST API; live network)
  - N-gram self-comparison   (datasketch MinHash)
"""

import sys, os, re, json
from pathlib import Path

# Make aegis importable from this directory
sys.path.insert(0, str(Path(__file__).parent))

TARGET = r"C:\IEEE\AIDEN\aiden_elsevier_paper_v2.docx"
REPORT_DIR = r"C:\IEEE\AIDEN"

# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("  AEGIS Academic Integrity Scanner")
print("  Target:", TARGET)
print("="*70)

# ---------------------------------------------------------------------------
# 1. Parse document
# ---------------------------------------------------------------------------
print("\n[1/5] Parsing document...")
from aegis.core.document import DocumentParser
parser = DocumentParser()
doc = parser.parse(TARGET)
print(f"      Words : {len(doc.full_text.split()):,}")
print(f"      Sections : {len(doc.sections)}")
print(f"      References found : {len(doc.references)}")
print(f"      Abstract : {'yes' if doc.abstract else 'no'}")

# ---------------------------------------------------------------------------
# 2. Stylometric analysis
# ---------------------------------------------------------------------------
print("\n[2/5] Running stylometric analysis...")
from aegis.detectors.stylometric import StylometricAnalyzer
stylo = StylometricAnalyzer(segment_size_words=300, change_threshold=0.40)
sresult = stylo.analyze(doc.full_text)
dp = sresult.document_profile

print(f"\n      --- Document Stylometric Profile ---")
print(f"      Word count              : {dp.word_count:,}")
print(f"      Avg sentence length     : {dp.avg_sentence_len} words")
print(f"      Std sentence length     : {dp.std_sentence_len} words")
print(f"      Type-token ratio (TTR)  : {dp.ttr:.4f}")
print(f"      Hapax legomena ratio    : {dp.hapax_ratio:.4f}")
print(f"      Yule's K                : {dp.yule_k:.2f}")
print(f"      Flesch-Kincaid grade    : {dp.readability_fk_grade}")
print(f"      Passive voice ratio     : {dp.passive_ratio:.3f}")
print(f"      Nominalization density  : {dp.nominalization_density} per 100 words")
print(f"      Hedge word density      : {dp.hedge_density} per 100 words")
print(f"      Punctuation density     : {dp.punct_density} per sentence")

print(f"\n      --- Style Consistency ---")
print(f"      Segments analyzed       : {len(sresult.segment_profiles)}")
print(f"      Consistency score       : {sresult.consistency_score:.3f} (1.0 = perfect)")
print(f"      Is consistent           : {'YES' if sresult.is_consistent else 'NO -- flagged'}")
flagged_segs = [cp for cp in sresult.change_points if cp.flagged]
if flagged_segs:
    print(f"\n      Flagged segments ({len(flagged_segs)}):")
    for cp in flagged_segs:
        print(f"        Seg {cp.segment_index:02d}: delta={cp.delta_distance:.3f} | {cp.text_preview[:80]}...")
else:
    print(f"      No segments flagged (all within delta threshold 0.40)")

if sresult.flags:
    for f in sresult.flags:
        print(f"      FLAG: {f}")

# Top function words
fw_pairs = list(zip(
    ["the","be","to","of","and","a","in","that","have","it",
     "for","not","on","with","he","as","you","do","at","this",
     "but","his","by","from","they","we","say","her","she","or",
     "an","will","my","one","all","would","there","their","what",
     "so","up","out","if","about","who","get","which","go","me","when"],
    dp.function_word_vector
))
fw_pairs.sort(key=lambda x: x[1], reverse=True)
print(f"\n      Top 10 function words by frequency:")
for w, freq in fw_pairs[:10]:
    bar = "#" * int(freq * 500)
    print(f"        {w:10s} {freq:.4f}  {bar}")

# ---------------------------------------------------------------------------
# 3. AI content heuristics (no GPT-2)
# ---------------------------------------------------------------------------
print("\n[3/5] Running AI content heuristics (no GPT-2 -- stylometric signals only)...")
from aegis.detectors.ai_detector import AIContentDetector, HEDGE_PHRASES
det_ai = AIContentDetector()

paragraphs = det_ai._split_paragraphs(doc.full_text, min_words=40)
print(f"      Paragraphs analyzed     : {len(paragraphs)}")

para_scores = []
for para in paragraphs:
    burst = det_ai._burstiness(para)
    style = det_ai._stylometric_ai_score(para)
    # Without GPT-2 we use only burstiness + stylometric (equal weight)
    score = 0.50 * (1.0 - min(burst / 0.35, 1.0)) + 0.50 * style
    para_scores.append((score, burst, style, para))

doc_ai_score = sum(s[0] for s in para_scores) / max(len(para_scores), 1)
ai_flagged = [s for s in para_scores if s[0] >= 0.55]

print(f"      Document AI heuristic score : {doc_ai_score:.3f} (0=human, 1=AI-like)")
print(f"      Paragraphs above 0.55 threshold : {len(ai_flagged)}")

if ai_flagged:
    print(f"\n      Most AI-like paragraphs (heuristic only -- no GPT-2):")
    for score, burst, style, para in sorted(ai_flagged, key=lambda x: -x[0])[:3]:
        print(f"        Score={score:.3f} | Burstiness={burst:.3f} | "
              f"StyleScore={style:.3f}")
        print(f"        Excerpt: {para[:120].strip()}...")
        print()
else:
    print("      No paragraphs triggered AI heuristic threshold")

# Hedge phrase count
hedge_count = sum(doc.full_text.lower().count(h) for h in HEDGE_PHRASES)
total_words = len(doc.full_text.split())
hedge_density = hedge_count / (total_words / 100)
print(f"\n      Hedge phrase density    : {hedge_density:.2f} per 100 words")
print(f"      (AI academic text typical: >5.0; human academic: 2-4)")

# Sentence length CV across the whole document
sentences = [s for s in re.split(r"(?<=[.!?])\s+", doc.full_text)
             if len(s.split()) > 3]
lengths = [len(s.split()) for s in sentences]
if lengths:
    mean_l = sum(lengths) / len(lengths)
    cv = (sum((l - mean_l)**2 for l in lengths) / len(lengths))**0.5 / max(mean_l, 1)
    print(f"      Sentence length CV      : {cv:.3f}")
    print(f"      (Human academic typical: 0.40-0.70; AI typical: <0.35)")

# ---------------------------------------------------------------------------
# 4. Citation integrity
# ---------------------------------------------------------------------------
print("\n[4/5] Running citation integrity check (Crossref live API)...")

if not doc.references:
    print("      No references extracted from DOCX -- loading from references.bib")
    # Try parsing the .bib file directly
    bib_path = r"C:\IEEE\AIDEN\references.bib"
    refs = []
    if Path(bib_path).exists():
        try:
            import bibtexparser
            with open(bib_path, encoding="utf-8") as f:
                bib = bibtexparser.load(f)
            for entry in bib.entries:
                from aegis.core.document import ParsedReference
                doi = entry.get("doi", "").strip()
                year = entry.get("year", "").strip()
                title = entry.get("title", "").strip().replace("{","").replace("}","")
                author_raw = entry.get("author", "")
                authors = [a.strip() for a in re.split(r" and ", author_raw)]
                refs.append(ParsedReference(
                    raw=str(entry),
                    authors=authors,
                    year=year if year else None,
                    title=title if title else None,
                    doi=doi if doi else None,
                    url=None,
                    journal=entry.get("journal", entry.get("booktitle", None)),
                    cite_key=entry.get("ID", None),
                    line_number=None,
                ))
            print(f"      Loaded {len(refs)} references from references.bib")
        except ImportError:
            print("      bibtexparser not installed; using inline DOI extraction")
            refs = []
    doc_refs = refs
else:
    doc_refs = doc.references
    print(f"      Using {len(doc_refs)} references parsed from DOCX")

# Also extract DOIs directly from full text as fallback
if not doc_refs:
    doi_pattern = re.compile(r'10\.\d{4,}/\S+')
    raw_dois = list(set(doi_pattern.findall(doc.full_text)))
    print(f"      Fallback: extracted {len(raw_dois)} DOIs from raw text")
    from aegis.core.document import ParsedReference
    doc_refs = []
    for doi in raw_dois:
        doi = doi.rstrip(".,;)")
        doc_refs.append(ParsedReference(
            raw=doi, authors=[], year=None, title=None,
            doi=doi, url=None, journal=None,
            cite_key=doi.split("/")[-1][:20], line_number=None,
        ))

from aegis.detectors.citation import CitationIntegrityDetector
cdet = CitationIntegrityDetector(
    email="sunil.gentyala@ieee.org",
    verify_timeout=10.0,
    min_title_similarity=0.60,
)

if doc_refs:
    print(f"      Verifying {len(doc_refs)} reference(s) against Crossref...\n")
    verdicts = cdet.verify_references(doc_refs)
    summary = cdet.summary(verdicts)

    col = {"VALID":"OK   ","MISMATCH":"WARN ","HALLUCINATED":"FAIL ",
           "UNRESOLVABLE":"ERR  ","NO_DOI":"INFO "}
    for v in verdicts:
        tag = col.get(v.verdict, "?    ")
        title_disp = (v.claimed_title or "N/A")[:55]
        print(f"      [{tag}] {(v.cite_key or 'unknown')[:18]:18s} "
              f"{v.verdict:12s} conf={v.confidence:.2f}  {title_disp}")
        for issue in v.issues:
            print(f"              Issue: {issue}")

    print(f"\n      --- Citation Integrity Summary ---")
    print(f"      Total references verified : {summary['total_references']}")
    print(f"      Verdict breakdown         : {summary['verdict_counts']}")
    print(f"      Flagged (MISMATCH+HALL.)  : {summary['flagged_count']}")
    print(f"      Citation integrity score  : {summary['citation_integrity_score']:.3f}")
    print(f"      Risk level                : {summary['risk_level']}")
else:
    verdicts = []
    summary = {}
    print("      No references available to verify")

# ---------------------------------------------------------------------------
# 5. N-gram self-consistency check
# ---------------------------------------------------------------------------
print("\n[5/5] N-gram analysis (intra-document repetition)...")
from aegis.detectors.ngram import NGramDetector
ngram = NGramDetector(word_n=3, char_n=5, word_threshold=0.40, char_threshold=0.55)

# Split into sections and compare each against the others
sections_text = [s.text for s in doc.sections if len(s.text.split()) > 80]
if len(sections_text) >= 2:
    high_overlap_pairs = []
    for i in range(len(sections_text)):
        for j in range(i+1, len(sections_text)):
            res = ngram.compare(sections_text[i], sections_text[j])
            if res["combined_score"] >= 0.15:
                label_i = doc.sections[i].title[:40] if i < len(doc.sections) else f"sec{i}"
                label_j = doc.sections[j].title[:40] if j < len(doc.sections) else f"sec{j}"
                high_overlap_pairs.append((res["combined_score"], label_i, label_j, res))

    if high_overlap_pairs:
        high_overlap_pairs.sort(key=lambda x: -x[0])
        print(f"      Section pairs with notable lexical overlap:")
        for score, li, lj, res in high_overlap_pairs[:5]:
            print(f"        {li[:35]:35s} vs {lj[:35]:35s}")
            print(f"          word-J={res['word_ngram_jaccard']:.3f}  "
                  f"char-J={res['char_ngram_jaccard']:.3f}  combined={res['combined_score']:.3f}")
    else:
        print("      No high intra-document n-gram overlap detected")
else:
    print(f"      {len(sections_text)} section(s) found with >80 words -- pairwise comparison skipped")

# Vocabulary richness across whole doc
tokens = re.findall(r"\b[a-z]{2,}\b", doc.full_text.lower())
freq = {}
for t in tokens:
    freq[t] = freq.get(t, 0) + 1
vocab = len(freq)
hapax = sum(1 for c in freq.values() if c == 1)
print(f"\n      Vocabulary statistics:")
print(f"        Total word tokens      : {len(tokens):,}")
print(f"        Unique words (vocab)   : {vocab:,}")
print(f"        Hapax legomena         : {hapax:,} ({hapax/vocab*100:.1f}% of vocab)")
print(f"        Type-token ratio       : {vocab/len(tokens):.4f}")
print(f"        Top 20 content words   :")
content_stops = {"the","be","to","of","and","a","in","that","have","it","for","not",
                 "on","with","as","by","from","they","we","this","an","is","are","was",
                 "were","or","at","but","which","their","can","also","such","our","these",
                 "has","been","more","its","than","may","using","used","each","into"}
content_words = [(w,c) for w,c in freq.items()
                 if w not in content_stops and len(w) > 3]
content_words.sort(key=lambda x: -x[1])
for w, c in content_words[:20]:
    print(f"          {w:20s} {c:4d}")

# ---------------------------------------------------------------------------
# Generate JSON report
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("  OVERALL ASSESSMENT")
print("="*70)

# Compute aggregate risk
citation_risk = summary.get("risk_level", "LOW") if summary else "LOW"
flagged_ratio = (summary.get("flagged_count", 0) / max(summary.get("total_references",1),1)
                 if summary else 0.0)
style_risk = "HIGH" if not sresult.is_consistent else "LOW"
ai_risk = ("MEDIUM" if doc_ai_score > 0.50 else "LOW")

risk_levels = [citation_risk, style_risk, ai_risk]
if "HIGH" in risk_levels or flagged_ratio > 0.3:
    overall = "HIGH"
elif "MEDIUM" in risk_levels or flagged_ratio > 0.1:
    overall = "MEDIUM"
else:
    overall = "LOW"

print(f"\n  Stylometric consistency : {sresult.consistency_score:.3f}  [{style_risk}]")
print(f"  AI heuristic score      : {doc_ai_score:.3f}  [{ai_risk}]")
print(f"  Citation integrity      : {summary.get('citation_integrity_score', 'N/A')}  [{citation_risk}]")
print(f"  Hedge density           : {hedge_density:.2f} per 100 words")
print(f"  FK readability grade    : {dp.readability_fk_grade}")
print(f"  Passive voice ratio     : {dp.passive_ratio:.3f}")
print(f"\n  OVERALL RISK: {overall}")
print()

all_flags = list(sresult.flags)
if doc_ai_score > 0.50:
    all_flags.append(f"AI heuristic score {doc_ai_score:.3f} above 0.50 threshold (heuristic only; GPT-2 not available)")
hallucinated = [v for v in verdicts if v.verdict == "HALLUCINATED"]
if hallucinated:
    all_flags.append(f"{len(hallucinated)} hallucinated citation(s) detected")

if all_flags:
    print("  Flags:")
    for f in all_flags:
        print(f"    - {f}")
else:
    print("  No integrity flags raised.")

# Save JSON summary
report = {
    "tool": "AEGIS v1.0.0",
    "target": TARGET,
    "overall_risk": overall,
    "stylometric": {
        "word_count": dp.word_count,
        "avg_sentence_len": dp.avg_sentence_len,
        "ttr": dp.ttr,
        "hapax_ratio": dp.hapax_ratio,
        "yule_k": dp.yule_k,
        "fk_grade": dp.readability_fk_grade,
        "passive_ratio": dp.passive_ratio,
        "nominalization_density": dp.nominalization_density,
        "hedge_density": dp.hedge_density,
        "punct_density": dp.punct_density,
        "consistency_score": sresult.consistency_score,
        "is_consistent": sresult.is_consistent,
        "flagged_segments": len(flagged_segs),
        "segments_analyzed": len(sresult.segment_profiles),
        "flags": sresult.flags,
    },
    "ai_heuristics": {
        "note": "GPT-2 not installed; stylometric signals only",
        "document_score": round(doc_ai_score, 3),
        "paragraphs_analyzed": len(para_scores),
        "paragraphs_flagged": len(ai_flagged),
        "hedge_density_per_100w": round(hedge_density, 2),
        "sentence_length_cv": round(cv, 3) if lengths else None,
    },
    "citation_integrity": {
        "references_verified": len(verdicts),
        "verdicts": {v.cite_key: v.verdict for v in verdicts},
        "summary": summary,
        "flags": [v.cite_key + ": " + "; ".join(v.issues)
                  for v in verdicts if v.issues],
    },
    "flags": all_flags,
}

out_path = Path(REPORT_DIR) / "aegis_scan_aiden_v2.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"\n  JSON report saved: {out_path}")
print("="*70 + "\n")
