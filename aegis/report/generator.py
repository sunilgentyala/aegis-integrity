"""
Report generator: produces JSON + styled HTML reports from AnalysisReport.

HTML output is self-contained (no external CDN calls) so it can be
attached to an email or opened offline. Includes:
  - Executive summary with colour-coded risk badge
  - Per-detector expandable sections
  - Flagged passage table with source attribution
  - Citation verdict table
  - Stylometric segment heatmap (text preview)
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aegis import __version__ as AEGIS_VERSION
from aegis.core.pipeline import AnalysisReport


class ReportGenerator:

    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_json(self, report: AnalysisReport, filename: Optional[str] = None) -> str:
        """Serialize report to JSON. Returns absolute path."""
        data = self._report_to_dict(report)
        fname = filename or f"aegis_report_{self._stem(report)}.json"
        path = self.output_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(path)

    def generate_html(self, report: AnalysisReport, filename: Optional[str] = None) -> str:
        """Render HTML report. Returns absolute path."""
        data = self._report_to_dict(report)
        html = self._render_html(data, report)
        fname = filename or f"aegis_report_{self._stem(report)}.html"
        path = self.output_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return str(path)

    def generate_batch_html(self, result, filename: str = "aegis_batch_report.html") -> str:
        """Render a standalone HTML report for a BatchAnalysisResult
        (essay-mill / classroom cross-document analysis). Returns absolute path."""
        html = self._render_batch_html(result)
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return str(path)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _report_to_dict(self, r: AnalysisReport) -> dict:
        d: dict = {
            "aegis_version": AEGIS_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "submission": r.submission_path,
            "elapsed_seconds": r.elapsed_seconds,
            "overall_risk": r.overall_risk,
            "flags": r.flags,
            "network_activity": r.network_activity,
            "detector_status": r.detector_status,
            "scores": {
                "plagiarism": r.plagiarism_score,
                "ai_content": r.ai_score,
                "citation_issue_rate": r.citation_score,
                "style_inconsistency": r.style_score,
                "self_recycling_pct": round(r.self_recycle_score * 100, 1),
            },
        }

        # N-gram matches
        d["ngram_matches"] = [
            {
                "source": m.source_label,
                "jaccard": m.jaccard_estimate,
                "type": m.match_type,
                "submission_snippet": m.query_segment[:200],
                "source_snippet": m.source_segment[:200],
            }
            for m in r.ngram_matches[:20]  # top 20
        ]

        # Semantic matches
        d["semantic_matches"] = [
            {
                "source": m.source_label,
                "cosine": m.cosine_score,
                "rerank": m.rerank_score,
                "is_paraphrase": m.is_paraphrase,
                "submission_snippet": m.query_sentence[:200],
                "source_snippet": m.source_sentence[:200],
            }
            for m in r.semantic_matches[:20]
        ]

        # AI detection
        if r.ai_result:
            ai = r.ai_result
            d["ai_detection"] = {
                "verdict": ai.document_verdict,
                "ensemble_score": ai.document_ensemble_score,
                "ai_paragraph_fraction": ai.ai_fraction,
                "detected_language": ai.detected_language,
                "esl_calibration_applied": ai.calibration_applied,
                "summary": ai.summary,
                "paragraphs": [
                    {
                        "text": p.text[:150],
                        "verdict": p.verdict,
                        "ensemble_score": p.ensemble_score,
                        "perplexity": p.perplexity,
                        "burstiness": p.burstiness,
                        "gpt_tell_density": p.gpt_tell_density,
                    }
                    for p in ai.paragraph_scores
                ],
            }

        # Citation integrity
        d["citation_summary"] = r.citation_summary
        d["citation_integrity"] = [
            {
                "cite_key": v.cite_key,
                "verdict": v.verdict,
                "confidence": v.confidence,
                "doi": v.doi,
                "claimed_title": (v.claimed_title or "")[:100],
                "resolved_title": (v.resolved_title or "")[:100],
                "issues": v.issues,
            }
            for v in r.citation_verdicts
        ]

        # Stylometric
        if r.stylometric_result:
            st = r.stylometric_result
            d["stylometric"] = {
                "is_consistent": st.is_consistent,
                "consistency_score": st.consistency_score,
                "author_deviation": st.author_deviation,
                "flags": st.flags,
                "change_points": [
                    {
                        "segment": cp.segment_index,
                        "delta": cp.delta_distance,
                        "flagged": cp.flagged,
                        "reason": cp.reason,
                        "preview": cp.text_preview[:120],
                    }
                    for cp in st.change_points
                ],
                "document_profile": {
                    "avg_sentence_len": st.document_profile.avg_sentence_len,
                    "ttr": st.document_profile.ttr,
                    "readability_fk_grade": st.document_profile.readability_fk_grade,
                    "passive_ratio": st.document_profile.passive_ratio,
                    "hedge_density": st.document_profile.hedge_density,
                    "yule_k": st.document_profile.yule_k,
                },
            }

        # Self-plagiarism
        if r.self_plagiarism_result:
            sp = r.self_plagiarism_result
            d["self_plagiarism"] = {
                "overall_overlap_pct": sp.overall_overlap_pct,
                "risk_level": sp.risk_level,
                "source_breakdown": sp.source_breakdown,
                "flags": sp.flags,
                "cope_guidance": sp.cope_guidance,
                "passages": [
                    {
                        "source": p.source_label,
                        "overlap_type": p.overlap_type,
                        "risk": p.risk_level,
                        "char_jaccard": p.char_jaccard,
                        "word_jaccard": p.word_jaccard,
                        "semantic_score": p.semantic_score,
                        "submission": p.submission_text[:200],
                        "source_text": p.source_text[:200],
                    }
                    for p in sp.recycled_passages[:30]
                ],
            }

        # Watermark analysis (experimental heuristic / verified-scheme hook)
        if r.watermark_result:
            wr = r.watermark_result
            d["watermark"] = {
                "mode": wr.mode.value,
                "status": wr.status.value,
                "verdict": wr.verdict,
                "evidence_status": wr.evidence_status,
                "affects_overall_risk": wr.affects_overall_risk,
                "watermark_scheme": wr.watermark_scheme,
                "tokenizer_name": wr.tokenizer_name,
                "configuration_validated": wr.configuration_validated,
                "tokens_evaluated": wr.tokens_evaluated,
                "minimum_tokens_required": wr.minimum_tokens_required,
                "z_score": wr.z_score,
                "p_value": wr.p_value,
                "confidence": wr.confidence,
                "warnings": wr.warnings,
                "limitations": wr.limitations,
                "error_code": wr.error_code,
                "detector_version": wr.detector_version,
            }

        # Citation network analysis (self-citation, predatory venues, clustering)
        if r.citation_network_result:
            cn = r.citation_network_result
            d["citation_network"] = {
                "total_references": cn.total_references,
                "self_citation_count": cn.self_citation_count,
                "self_citation_rate": cn.self_citation_rate,
                "predatory_journal_count": cn.predatory_journal_count,
                "missing_doi_rate": cn.missing_doi_rate,
                "year_span": list(cn.year_span),
                "venue_concentration": cn.venue_concentration,
                "overall_risk": cn.overall_risk,
                "openalex_queried": cn.openalex_queried,
                "flags": [
                    {
                        "type": f.flag_type,
                        "severity": f.severity,
                        "message": f.message,
                        "affected_refs": f.affected_refs,
                    }
                    for f in cn.flags
                ],
            }

        # Semantic coherence / AI-polish analysis
        if r.coherence_result:
            co = r.coherence_result
            d["coherence"] = {
                "verdict": co.verdict,
                "ensemble_score": co.ensemble_score,
                "confidence": co.confidence,
                "discourse_connector_density": co.discourse_connector_density,
                "sentence_length_cv": co.sentence_length_cv,
                "mtld_score": co.mtld_score,
                "hedging_density": co.hedging_density,
                "section_template_match": co.section_template_match,
                "flags": [
                    {
                        "signal": f.signal,
                        "value": f.value,
                        "threshold": f.threshold,
                        "message": f.message,
                    }
                    for f in co.flags
                ],
            }

        # Target-publisher verification (IEEE/ACM/Elsevier/IET/IETE/BCS)
        if r.venue_verification_result:
            vv = r.venue_verification_result
            d["venue_verification"] = {
                "target_publishers": vv.target_publishers,
                "citations_by_publisher": vv.citations_by_publisher,
                "overall_risk": vv.overall_risk,
                "queried": vv.queried,
                "prior_publication_matches": [
                    {
                        "publisher": m.publisher,
                        "title": m.title,
                        "doi": m.doi,
                        "year": m.year,
                        "similarity": m.title_similarity,
                        "url": m.url,
                    }
                    for m in vv.prior_publication_matches
                ],
                "flags": [
                    {
                        "type": f.flag_type,
                        "severity": f.severity,
                        "message": f.message,
                        "cite_key": f.cite_key,
                    }
                    for f in vv.flags
                ],
            }

        # Mathematical formula checking (v3.0; compliance signal only)
        if r.math_result:
            m = r.math_result
            d["math_check"] = {
                "equations_found": m.equations_found,
                "equation_numbers": m.equation_numbers,
                "extraction_method": m.extraction_method,
                "limitations": m.limitations,
                "issues": [
                    {"category": i.category, "severity": i.severity,
                     "message": i.message, "rule_source": i.rule_source}
                    for i in m.all_issues
                ],
            }

        # Grammar & language convention checking (v3.0; compliance signal only)
        if r.grammar_result:
            g = r.grammar_result
            d["grammar_check"] = {
                "word_count": g.word_count,
                "sentence_count": g.sentence_count,
                "avg_sentence_length": g.avg_sentence_length,
                "spelling_variant_detected": g.spelling_variant_detected,
                "spelling_variant_counts": g.spelling_variant_counts,
                "contraction_count": g.contraction_count,
                "quality_score": g.quality_score,
                "nlp_backend": g.nlp_backend,
                "issues": [
                    {"category": i.category, "severity": i.severity,
                     "message": i.message, "count": i.count,
                     "examples": i.examples, "rule_source": i.rule_source}
                    for i in g.issues
                ],
            }

        # Per-venue guideline compliance (v3.0; run separately per venue)
        if r.guideline_results:
            d["guideline_compliance"] = {
                venue: {
                    "display_name": res.display_name,
                    "source_name": res.source_name,
                    "source_url": res.source_url,
                    "overall_status": res.overall_status,
                    "checks": [
                        {"rule": c.rule, "status": c.status,
                         "detail": c.detail, "source": c.source}
                        for c in res.checks
                    ],
                }
                for venue, res in r.guideline_results.items()
            }

        return d

    # ------------------------------------------------------------------
    # HTML rendering
    # ------------------------------------------------------------------

    RISK_COLORS = {
        "LOW": "#27ae60",
        "MEDIUM": "#f39c12",
        "HIGH": "#e74c3c",
        "CRITICAL": "#8e1a0e",
        "UNKNOWN": "#95a5a6",
    }

    VERDICT_COLORS = {
        "VALID": "#27ae60",
        "NO_DOI": "#95a5a6",
        "UNRESOLVABLE": "#f39c12",
        "MISMATCH": "#e67e22",
        "HALLUCINATED": "#c0392b",
        "HUMAN": "#27ae60",
        "UNCERTAIN": "#f39c12",
        "AI_LIKELY": "#e67e22",
        "AI_DETECTED": "#c0392b",
        "SKIPPED": "#95a5a6",
        "NO_STATISTICAL_ANOMALY": "#27ae60",
        "STATISTICAL_ANOMALY": "#f39c12",
        "INSUFFICIENT_TEXT": "#95a5a6",
        "UNSUPPORTED_CONFIGURATION": "#95a5a6",
        "ANALYSIS_FAILED": "#c0392b",
        "VERIFIED_SCHEME_SIGNAL": "#e67e22",
    }

    def _render_html(self, data: dict, report: AnalysisReport) -> str:
        risk_color = self.RISK_COLORS.get(data["overall_risk"], "#95a5a6")
        flags_html = "".join(
            f'<li>{self._esc(f)}</li>' for f in data["flags"]
        ) or "<li>No flags raised.</li>"
        privacy_note = self._privacy_disclosure(data.get("network_activity", {}))

        ngram_rows = self._ngram_table_rows(data.get("ngram_matches", []))
        semantic_rows = self._semantic_table_rows(data.get("semantic_matches", []))
        citation_rows = self._citation_table_rows(data.get("citation_integrity", []))
        ai_section = self._ai_section(data.get("ai_detection"))
        stylo_section = self._stylo_section(data.get("stylometric"))
        self_plag_section = self._self_plag_section(data.get("self_plagiarism"))
        watermark_section = self._watermark_section(data.get("watermark"))
        citation_network_section = self._citation_network_section(data.get("citation_network"))
        coherence_section = self._coherence_section(data.get("coherence"))
        venue_verification_section = self._venue_verification_section(data.get("venue_verification"))
        math_section = self._math_section(data.get("math_check"))
        grammar_section = self._grammar_section(data.get("grammar_check"))
        guideline_section = self._guideline_section(data.get("guideline_compliance"))

        scores = data["scores"]

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>AEGIS Integrity Report</title>
<style>
  body {{font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 0; padding: 0; background: #f5f7fa; color: #2c3e50;}}
  .container {{max-width: 1100px; margin: 0 auto; padding: 24px;}}
  h1 {{font-size: 1.8rem; margin-bottom: 4px;}}
  h2 {{font-size: 1.2rem; border-bottom: 2px solid #ecf0f1; padding-bottom: 6px;
       margin-top: 32px;}}
  .badge {{display: inline-block; padding: 6px 18px; border-radius: 20px;
           color: #fff; font-weight: 700; font-size: 1.1rem;
           background: {risk_color};}}
  .meta {{color: #7f8c8d; font-size: 0.85rem; margin-bottom: 20px;}}
  .scores {{display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0;}}
  .score-card {{background: #fff; border-radius: 8px; padding: 14px 20px;
               box-shadow: 0 1px 4px rgba(0,0,0,.08); min-width: 140px;}}
  .score-card .label {{font-size: 0.75rem; color: #7f8c8d; text-transform: uppercase;}}
  .score-card .value {{font-size: 1.5rem; font-weight: 700;}}
  .flags {{background: #fef9e7; border-left: 4px solid #f39c12;
           padding: 12px 16px; border-radius: 4px; margin: 16px 0;}}
  .flags ul {{margin: 0; padding-left: 20px;}}
  table {{width: 100%; border-collapse: collapse; font-size: 0.87rem;
          background: #fff; border-radius: 8px; overflow: hidden;
          box-shadow: 0 1px 4px rgba(0,0,0,.08);}}
  th {{background: #2c3e50; color: #fff; padding: 10px 12px; text-align: left;}}
  td {{padding: 8px 12px; border-bottom: 1px solid #ecf0f1; vertical-align: top;}}
  tr:last-child td {{border-bottom: none;}}
  tr:hover td {{background: #f8f9fa;}}
  .verdict {{display: inline-block; padding: 2px 8px; border-radius: 10px;
             color: #fff; font-size: 0.78rem; font-weight: 600;}}
  details summary {{cursor: pointer; font-weight: 600; padding: 8px 0; color: #2980b9;}}
  .section {{background: #fff; border-radius: 8px; padding: 18px 20px;
             box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-top: 12px;}}
  .no-data {{color: #95a5a6; font-style: italic;}}
  footer {{margin-top: 40px; color: #bdc3c7; font-size: 0.78rem; text-align: center;}}
</style>
</head>
<body>
<div class="container">
  <h1>AEGIS Academic Integrity Report</h1>
  <div class="meta">
    Generated: {data['generated_at']} &nbsp;|&nbsp;
    File: <code>{self._esc(data['submission'])}</code> &nbsp;|&nbsp;
    Analysis time: {data['elapsed_seconds']}s
  </div>
  <div class="meta">{privacy_note}</div>

  <span class="badge">Overall Risk: {data['overall_risk']}</span>

  <div class="scores">
    {self._score_card("Plagiarism", f"{scores['plagiarism']:.2f}")}
    {self._score_card("AI Content", f"{scores['ai_content']:.2f}")}
    {self._score_card("Citation Issues", f"{scores['citation_issue_rate']:.0%}")}
    {self._score_card("Style Inconsistency", f"{scores['style_inconsistency']:.2f}")}
    {self._score_card("Self-Recycling", f"{scores['self_recycling_pct']:.1f}%")}
  </div>

  <div class="flags">
    <strong>Flags:</strong>
    <ul>{flags_html}</ul>
  </div>

  <!-- N-gram similarity -->
  <h2>N-Gram Similarity (MinHash LSH)</h2>
  <div class="section">
    {"<p class='no-data'>No significant n-gram matches found.</p>" if not ngram_rows else
     f"<table><thead><tr><th>Source</th><th>Type</th><th>Jaccard</th>"
     f"<th>Submission excerpt</th><th>Source excerpt</th></tr></thead>"
     f"<tbody>{ngram_rows}</tbody></table>"}
  </div>

  <!-- Semantic similarity -->
  <h2>Semantic Similarity (SBERT Dense Retrieval)</h2>
  <div class="section">
    {"<p class='no-data'>No semantic paraphrase matches found.</p>" if not semantic_rows else
     f"<table><thead><tr><th>Source</th><th>Cosine</th><th>Paraphrase?</th>"
     f"<th>Submission sentence</th><th>Source sentence</th></tr></thead>"
     f"<tbody>{semantic_rows}</tbody></table>"}
  </div>

  <!-- AI detection -->
  <h2>AI Content Detection</h2>
  <div class="section">{ai_section}</div>

  <!-- Citation integrity -->
  <h2>Citation Integrity (Crossref Verification)</h2>
  <div class="section">
    {"<p class='no-data'>No references found or citation check was skipped.</p>"
     if not citation_rows else
     f"<table><thead><tr><th>Key</th><th>Verdict</th><th>DOI</th>"
     f"<th>Issues</th><th>Claimed title</th></tr></thead>"
     f"<tbody>{citation_rows}</tbody></table>"}
  </div>

  <!-- Citation network -->
  <h2>Citation Network Analysis (Self-Citation, Predatory Venues, Clustering)</h2>
  <div class="section">{citation_network_section}</div>

  <!-- Target-publisher verification -->
  <h2>Target-Publisher Verification (IEEE / ACM / Elsevier / IET / IETE / BCS)</h2>
  <div class="section">{venue_verification_section}</div>

  <!-- Stylometric -->
  <h2>Stylometric Analysis (Authorship Consistency)</h2>
  <div class="section">{stylo_section}</div>

  <!-- Semantic coherence -->
  <h2>Semantic Coherence Analysis (AI-Polish Detection)</h2>
  <div class="section">{coherence_section}</div>

  <!-- Self-plagiarism -->
  <h2>Self-Plagiarism / Text Recycling</h2>
  <div class="section">{self_plag_section}</div>

  <!-- Watermark analysis -->
  <h2>LLM Watermark Analysis</h2>
  <div class="section">{watermark_section}</div>

  <!-- Math + grammar compliance (informational -- never affects overall risk) -->
  <h2>Mathematical Formula Check <small style="font-weight:400;color:#7f8c8d;">(compliance signal, not misconduct)</small></h2>
  <div class="section">{math_section}</div>

  <h2>Grammar &amp; Language Convention Check <small style="font-weight:400;color:#7f8c8d;">(compliance signal, not misconduct)</small></h2>
  <div class="section">{grammar_section}</div>

  <!-- Per-venue guideline compliance -->
  <h2>Publisher Guideline Compliance (IEEE / ACM / BCS / IET / ISACA / Elsevier, checked separately)</h2>
  <div class="section">{guideline_section}</div>

  <footer>AEGIS Academic Integrity Tool v{AEGIS_VERSION} &mdash; open-source</footer>
</div>
</body>
</html>"""

    def _render_batch_html(self, result) -> str:
        risk_color = self.RISK_COLORS.get(result.overall_risk, "#95a5a6")
        flags_html = "".join(
            f"<li>{self._esc(f)}</li>" for f in result.flags
        ) or "<li>No flags raised.</li>"

        pair_rows = "".join(
            f"<tr><td>{self._esc(p.doc_a)}</td><td>{self._esc(p.doc_b)}</td>"
            f"<td>{p.ngram_similarity:.3f}</td><td>{p.vocab_overlap:.3f}</td>"
            f"<td>{p.section_sequence_match:.3f}</td><td>{p.combined_score:.3f}</td>"
            f"<td><small>{self._esc(p.reason)}</small></td></tr>"
            for p in result.suspicious_pairs
        )
        pairs_section = (
            "<p class='no-data'>No suspicious pairs found.</p>" if not pair_rows else
            f"<table><thead><tr><th>Doc A</th><th>Doc B</th><th>N-gram</th>"
            f"<th>Vocab</th><th>Sections</th><th>Combined</th><th>Reason</th></tr></thead>"
            f"<tbody>{pair_rows}</tbody></table>"
        )

        clusters_html = (
            "<ul>" + "".join(
                f"<li>{self._esc(', '.join(grp))}</li>" for grp in result.cluster_groups
            ) + "</ul>"
        ) if result.cluster_groups else "<p class='no-data'>No submission clusters detected.</p>"

        high_ai_html = (
            "<p>" + self._esc(", ".join(result.high_ai_cluster)) + "</p>"
        ) if result.high_ai_cluster else "<p class='no-data'>None.</p>"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>AEGIS Batch / Classroom Report</title>
<style>
  body {{font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 0; padding: 0; background: #f5f7fa; color: #2c3e50;}}
  .container {{max-width: 1100px; margin: 0 auto; padding: 24px;}}
  h1 {{font-size: 1.8rem; margin-bottom: 4px;}}
  h2 {{font-size: 1.2rem; border-bottom: 2px solid #ecf0f1; padding-bottom: 6px;
       margin-top: 32px;}}
  .badge {{display: inline-block; padding: 6px 18px; border-radius: 20px;
           color: #fff; font-weight: 700; font-size: 1.1rem;
           background: {risk_color};}}
  table {{width: 100%; border-collapse: collapse; font-size: 0.87rem;
          background: #fff; border-radius: 8px; overflow: hidden;
          box-shadow: 0 1px 4px rgba(0,0,0,.08);}}
  th {{background: #2c3e50; color: #fff; padding: 10px 12px; text-align: left;}}
  td {{padding: 8px 12px; border-bottom: 1px solid #ecf0f1; vertical-align: top;}}
  .section {{background: #fff; border-radius: 8px; padding: 18px 20px;
             box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-top: 12px;}}
  .flags {{background: #fef9e7; border-left: 4px solid #f39c12;
           padding: 12px 16px; border-radius: 4px; margin: 16px 0;}}
  .no-data {{color: #95a5a6; font-style: italic;}}
  footer {{margin-top: 40px; color: #bdc3c7; font-size: 0.78rem; text-align: center;}}
</style>
</head>
<body>
<div class="container">
  <h1>AEGIS Batch / Classroom Report</h1>
  <span class="badge">Overall Risk: {result.overall_risk}</span>
  <p>Submissions analyzed: {result.submission_count} &nbsp;|&nbsp;
     Mean AI score: {result.mean_ai_score:.3f} (std {result.ai_score_std:.3f})</p>

  <div class="flags"><strong>Flags:</strong><ul>{flags_html}</ul></div>

  <h2>Suspicious Pairs</h2>
  <div class="section">{pairs_section}</div>

  <h2>Cluster Groups (Suspected Shared Source)</h2>
  <div class="section">{clusters_html}</div>

  <h2>High AI-Score Cluster</h2>
  <div class="section">{high_ai_html}</div>

  <footer>AEGIS Academic Integrity Tool v{AEGIS_VERSION} &mdash; open-source</footer>
</div>
</body>
</html>"""

    # ------------------------------------------------------------------
    # HTML sub-sections
    # ------------------------------------------------------------------

    def _score_card(self, label: str, value: str) -> str:
        return (f'<div class="score-card"><div class="label">{label}</div>'
                f'<div class="value">{value}</div></div>')

    def _verdict_badge(self, verdict: str) -> str:
        color = self.VERDICT_COLORS.get(verdict, "#95a5a6")
        return f'<span class="verdict" style="background:{color}">{verdict}</span>'

    def _ngram_table_rows(self, matches: list[dict]) -> str:
        rows = []
        for m in matches:
            rows.append(
                f"<tr><td>{self._esc(m['source'])}</td>"
                f"<td>{m['type']}</td>"
                f"<td>{m['jaccard']:.3f}</td>"
                f"<td><small>{self._esc(m['submission_snippet'][:120])}</small></td>"
                f"<td><small>{self._esc(m['source_snippet'][:120])}</small></td></tr>"
            )
        return "".join(rows)

    def _semantic_table_rows(self, matches: list[dict]) -> str:
        rows = []
        for m in matches:
            flag = "Yes" if m["is_paraphrase"] else "No"
            rows.append(
                f"<tr><td>{self._esc(m['source'])}</td>"
                f"<td>{m['cosine']:.3f}</td>"
                f"<td>{flag}</td>"
                f"<td><small>{self._esc(m['submission_snippet'][:120])}</small></td>"
                f"<td><small>{self._esc(m['source_snippet'][:120])}</small></td></tr>"
            )
        return "".join(rows)

    def _citation_table_rows(self, verdicts: list[dict]) -> str:
        rows = []
        for v in verdicts:
            issues = "; ".join(v.get("issues", [])) or "None"
            rows.append(
                f"<tr><td>{self._esc(v['cite_key'])}</td>"
                f"<td>{self._verdict_badge(v['verdict'])}</td>"
                f"<td><small>{self._esc(v.get('doi') or 'N/A')}</small></td>"
                f"<td><small>{self._esc(issues[:200])}</small></td>"
                f"<td><small>{self._esc((v.get('claimed_title') or '')[:80])}</small></td></tr>"
            )
        return "".join(rows)

    def _ai_section(self, ai: Optional[dict]) -> str:
        if not ai:
            return "<p class='no-data'>AI detection was skipped or unavailable.</p>"
        badge = self._verdict_badge(ai["verdict"])
        lang = ai.get("detected_language", "?")
        esl = " (ESL calibration applied)" if ai.get("esl_calibration_applied") else ""
        rows = "".join(
            f"<tr><td><small>{self._esc(p['text'][:100])}</small></td>"
            f"<td>{self._verdict_badge(p['verdict'])}</td>"
            f"<td>{p['ensemble_score']:.3f}</td>"
            f"<td>{p['perplexity']:.1f}</td>"
            f"<td>{p['burstiness']:.3f}</td></tr>"
            for p in ai.get("paragraphs", [])
        )
        table = (
            f"<details><summary>Per-paragraph scores ({len(ai.get('paragraphs', []))} paragraphs)</summary>"
            f"<table><thead><tr><th>Excerpt</th><th>Verdict</th><th>Score</th>"
            f"<th>Perplexity</th><th>Burstiness</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></details>"
            if rows else ""
        )
        return (
            f"<p>Document verdict: {badge} &nbsp; Score: {ai['ensemble_score']:.3f} "
            f"&nbsp; AI paragraphs: {ai['ai_paragraph_fraction']*100:.0f}% "
            f"&nbsp; Language: {lang}{esl}</p>"
            f"{table}"
        )

    def _stylo_section(self, st: Optional[dict]) -> str:
        if not st:
            return "<p class='no-data'>Stylometric analysis was skipped.</p>"
        consistent = "Yes" if st["is_consistent"] else "No"
        dev = f"{st['author_deviation']:.3f}" if st.get("author_deviation") else "N/A"
        flags_html = (
            "<ul>" + "".join(f"<li>{self._esc(f)}</li>" for f in st.get("flags", []))
            + "</ul>"
        ) if st.get("flags") else "<p>No style flags.</p>"

        change_rows = "".join(
            f"<tr><td>Seg {cp['segment']}</td>"
            f"<td>{cp['delta']:.3f}</td>"
            f"<td>{'Yes' if cp['flagged'] else 'No'}</td>"
            f"<td><small>{self._esc(cp['preview'][:100])}</small></td></tr>"
            for cp in st.get("change_points", [])
        )
        cp_table = (
            f"<details><summary>Segment change points</summary>"
            f"<table><thead><tr><th>Segment</th><th>Delta</th>"
            f"<th>Flagged</th><th>Preview</th></tr></thead>"
            f"<tbody>{change_rows}</tbody></table></details>"
            if change_rows else ""
        )
        dp = st.get("document_profile", {})
        return (
            f"<p>Consistent: <strong>{consistent}</strong> "
            f"(score: {st['consistency_score']:.3f}) &nbsp;|&nbsp; "
            f"Author deviation: {dev}</p>"
            f"<p>Document profile &mdash; Avg sentence length: {dp.get('avg_sentence_len','?')}, "
            f"TTR: {dp.get('ttr','?')}, FK Grade: {dp.get('readability_fk_grade','?')}, "
            f"Passive ratio: {dp.get('passive_ratio','?')}, "
            f"Hedge density: {dp.get('hedge_density','?')}, "
            f"Yule K: {dp.get('yule_k','?')}</p>"
            f"{flags_html}{cp_table}"
        )

    def _self_plag_section(self, sp: Optional[dict]) -> str:
        if not sp:
            return ("<p class='no-data'>Self-plagiarism check was skipped "
                    "or no prior works were provided.</p>")
        risk_color = self.RISK_COLORS.get(sp["risk_level"], "#95a5a6")
        badge = (f'<span class="verdict" style="background:{risk_color}">'
                 f'{sp["risk_level"]}</span>')
        rows = "".join(
            f"<tr><td>{self._esc(p['source'])}</td>"
            f"<td>{p['overlap_type']}</td>"
            f"<td>{p['char_jaccard']:.3f}</td>"
            f"<td>{p['word_jaccard']:.3f}</td>"
            f"<td>{p['semantic_score']:.3f}</td>"
            f"<td><small>{self._esc(p['submission'][:100])}</small></td>"
            f"<td><small>{self._esc(p['source_text'][:100])}</small></td></tr>"
            for p in sp.get("passages", [])
        )
        table = (
            f"<details><summary>Recycled passages ({len(sp.get('passages',[]))} found)</summary>"
            f"<table><thead><tr><th>Source</th><th>Type</th><th>Char J</th>"
            f"<th>Word J</th><th>Sem.</th><th>Submission</th>"
            f"<th>Prior work</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></details>"
            if rows else ""
        )
        breakdown = ", ".join(
            f"{self._esc(k)}: {v}%" for k, v in sp.get("source_breakdown", {}).items()
        ) or "N/A"
        return (
            f"<p>Overlap: <strong>{sp['overall_overlap_pct']:.1f}%</strong> "
            f"&nbsp; Risk: {badge}</p>"
            f"<p>By source: {breakdown}</p>"
            f"<p><em>COPE guidance:</em> {self._esc(sp['cope_guidance'])}</p>"
            f"{table}"
        )

    def _watermark_section(self, wm: Optional[dict]) -> str:
        if not wm:
            return "<p class='no-data'>Watermark analysis was skipped or unavailable.</p>"

        badge = ""
        if wm["evidence_status"] == "experimental":
            badge = ('<span class="verdict" style="background:#f39c12">'
                      'EXPERIMENTAL</span> ')

        affects = "Yes" if wm["affects_overall_risk"] else "No"
        scheme = wm.get("watermark_scheme") or "N/A"
        tokenizer = wm.get("tokenizer_name") or "N/A"

        disclaimer = ""
        if wm["evidence_status"] == "experimental":
            disclaimer = (
                "<p><em>Experimental watermark analysis identified a token-distribution "
                "anomaly.</em> The actual watermark scheme, tokenizer, and secret "
                "configuration are unknown. This result did not affect the overall "
                "integrity risk score and should not be treated as proof that the "
                "document was generated by AI.</p>"
                if wm["verdict"] == "STATISTICAL_ANOMALY" else
                "<p><em>Experimental token-distribution analysis found no statistical "
                "anomaly.</em> This heuristic does not affect the overall integrity "
                "risk score.</p>"
            )
        elif wm["evidence_status"] == "scheme_verified":
            disclaimer = (
                "<p><em>A statistical signal was detected for the configured watermark "
                "profile.</em> This result is provenance evidence and requires manual "
                "interpretation. It does not independently establish academic "
                "misconduct.</p>"
            )

        warnings_html = (
            "<ul>" + "".join(f"<li>{self._esc(w)}</li>" for w in wm.get("warnings", [])) + "</ul>"
            if wm.get("warnings") else ""
        )
        limitations_html = (
            "<details><summary>Limitations</summary><ul>"
            + "".join(f"<li>{self._esc(lim)}</li>" for lim in wm.get("limitations", []))
            + "</ul></details>"
            if wm.get("limitations") else ""
        )

        return (
            f"<p>{badge}Mode: <strong>{wm['mode']}</strong> &nbsp; "
            f"Status: {wm['status']} &nbsp; Verdict: {self._verdict_badge(wm['verdict'])}</p>"
            f"<p>Affects overall risk score: <strong>{affects}</strong> &nbsp;|&nbsp; "
            f"Scheme: {self._esc(scheme)} &nbsp;|&nbsp; "
            f"Tokenizer: {self._esc(tokenizer)}</p>"
            f"<p>Tokens evaluated: {wm.get('tokens_evaluated', 0)} "
            f"(minimum required: {wm.get('minimum_tokens_required', 0)}) &nbsp;|&nbsp; "
            f"z-score: {wm.get('z_score')} &nbsp;|&nbsp; p-value: {wm.get('p_value')}</p>"
            f"{disclaimer}{warnings_html}{limitations_html}"
        )

    def _citation_network_section(self, cn: Optional[dict]) -> str:
        if not cn:
            return "<p class='no-data'>Citation network analysis was skipped or unavailable.</p>"
        risk_color = self.RISK_COLORS.get(cn["overall_risk"], "#95a5a6")
        badge = (f'<span class="verdict" style="background:{risk_color}">'
                 f'{cn["overall_risk"]}</span>')
        flags_html = (
            "<ul>" + "".join(
                f"<li><strong>{self._esc(f['type'])}</strong> "
                f"({self._esc(f['severity'])}): {self._esc(f['message'])}</li>"
                for f in cn.get("flags", [])
            ) + "</ul>"
        ) if cn.get("flags") else "<p>No citation-network flags.</p>"
        year_span = cn.get("year_span") or [None, None]
        return (
            f"<p>Overall risk: {badge}</p>"
            f"<p>References: {cn['total_references']} &nbsp;|&nbsp; "
            f"Self-citation rate: {cn['self_citation_rate']*100:.1f}% "
            f"({cn['self_citation_count']} refs) &nbsp;|&nbsp; "
            f"Predatory journal matches: {cn['predatory_journal_count']} &nbsp;|&nbsp; "
            f"Missing-DOI rate: {cn['missing_doi_rate']*100:.1f}%</p>"
            f"<p>Year span: {year_span[0]}&ndash;{year_span[1]} &nbsp;|&nbsp; "
            f"Venue concentration (Herfindahl): {cn['venue_concentration']:.3f} &nbsp;|&nbsp; "
            f"OpenAlex queried: {'Yes' if cn.get('openalex_queried') else 'No'}</p>"
            f"{flags_html}"
        )

    def _venue_verification_section(self, vv: Optional[dict]) -> str:
        if not vv:
            return "<p class='no-data'>Target-publisher verification was skipped or unavailable.</p>"
        risk_color = self.RISK_COLORS.get(vv["overall_risk"], "#95a5a6")
        badge = (f'<span class="verdict" style="background:{risk_color}">'
                 f'{vv["overall_risk"]}</span>')
        counts = vv.get("citations_by_publisher", {})
        counts_str = " &nbsp;|&nbsp; ".join(
            f"{pub}: {n}" for pub, n in counts.items()
        ) or "none"
        matches = vv.get("prior_publication_matches", [])
        matches_html = (
            "<table><thead><tr><th>Publisher</th><th>Title</th>"
            "<th>Year</th><th>Similarity</th><th>DOI</th></tr></thead><tbody>"
            + "".join(
                f"<tr><td>{self._esc(m['publisher'])}</td>"
                f"<td>{self._esc(m['title'][:100])}</td>"
                f"<td>{self._esc(m.get('year') or '')}</td>"
                f"<td>{m['similarity']:.0%}</td>"
                f"<td>{self._esc(m.get('doi') or '')}</td></tr>"
                for m in matches
            ) + "</tbody></table>"
        ) if matches else "<p>No near-duplicate titles found under the target publishers.</p>"
        flags_html = (
            "<ul>" + "".join(
                f"<li><strong>{self._esc(f['type'])}</strong> "
                f"({self._esc(f['severity'])}): {self._esc(f['message'])}</li>"
                for f in vv.get("flags", [])
            ) + "</ul>"
        ) if vv.get("flags") else "<p>No target-publisher flags.</p>"
        return (
            f"<p>Overall risk: {badge} &nbsp; "
            f"Target publishers checked: {', '.join(vv.get('target_publishers', []))} "
            f"&nbsp;|&nbsp; Crossref queried: {'Yes' if vv.get('queried') else 'No'}</p>"
            f"<p>Verified citations by publisher: {counts_str}</p>"
            f"<p><strong>Duplicate / prior-publication search:</strong></p>"
            f"{matches_html}"
            f"{flags_html}"
        )

    def _coherence_section(self, co: Optional[dict]) -> str:
        if not co:
            return "<p class='no-data'>Semantic coherence analysis was skipped or unavailable.</p>"
        badge = self._verdict_badge(co["verdict"])
        flags_html = (
            "<ul>" + "".join(
                f"<li><strong>{self._esc(f['signal'])}</strong>: {self._esc(f['message'])} "
                f"(value {f['value']:.3f}, threshold {f['threshold']:.3f})</li>"
                for f in co.get("flags", [])
            ) + "</ul>"
        ) if co.get("flags") else "<p>No coherence flags.</p>"
        return (
            f"<p>Verdict: {badge} &nbsp; Score: {co['ensemble_score']:.3f} "
            f"&nbsp; Confidence: {co['confidence']:.2f}</p>"
            f"<p>Discourse connector density: {co['discourse_connector_density']:.2f} "
            f"&nbsp;|&nbsp; Sentence length CV: {co['sentence_length_cv']:.3f} "
            f"&nbsp;|&nbsp; MTLD: {co['mtld_score']:.2f}</p>"
            f"<p>Hedging density: {co['hedging_density']:.2f} "
            f"&nbsp;|&nbsp; Section template match: {co['section_template_match']*100:.0f}%</p>"
            f"{flags_html}"
        )

    GUIDELINE_STATUS_COLORS = {
        "PASS": "#27ae60", "COMPLIANT": "#27ae60",
        "NEEDS_REVIEW": "#f39c12",
        "NOT_ENOUGH_DATA": "#95a5a6",
    }

    def _status_badge(self, status: str) -> str:
        color = self.GUIDELINE_STATUS_COLORS.get(status, "#95a5a6")
        return f'<span class="verdict" style="background:{color}">{status}</span>'

    def _math_section(self, m: Optional[dict]) -> str:
        if not m:
            return "<p class='no-data'>Math formula check was skipped or unavailable.</p>"
        if not m.get("issues") and m.get("equations_found", 0) == 0:
            return "<p class='no-data'>No numbered equations were found in this document.</p>"
        rows = "".join(
            f"<tr><td>{self._esc(i['category'])}</td>"
            f"<td>{i['severity']}</td>"
            f"<td>{self._esc(i['message'])}</td>"
            f"<td><small>{self._esc(i['rule_source'])}</small></td></tr>"
            for i in m.get("issues", [])
        )
        table = (
            f"<table><thead><tr><th>Category</th><th>Severity</th>"
            f"<th>Issue</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>"
            if rows else "<p>No issues found among the detected equations.</p>"
        )
        limitations = (
            "<details><summary>Limitations</summary><ul>"
            + "".join(f"<li>{self._esc(lim)}</li>" for lim in m.get("limitations", []))
            + "</ul></details>"
        ) if m.get("limitations") else ""
        return (
            f"<p>Equations found: <strong>{m['equations_found']}</strong> "
            f"(extraction method: {self._esc(m['extraction_method'])})</p>"
            f"{table}{limitations}"
        )

    def _grammar_section(self, g: Optional[dict]) -> str:
        if not g:
            return "<p class='no-data'>Grammar &amp; language check was skipped or unavailable.</p>"
        rows = "".join(
            f"<tr><td>{self._esc(i['category'])}</td>"
            f"<td>{i['severity']}</td>"
            f"<td>{i['count']}</td>"
            f"<td>{self._esc(i['message'])}</td></tr>"
            for i in g.get("issues", [])
        )
        table = (
            f"<table><thead><tr><th>Category</th><th>Severity</th>"
            f"<th>Count</th><th>Issue</th></tr></thead><tbody>{rows}</tbody></table>"
            if rows else "<p>No mechanical grammar/usage issues found.</p>"
        )
        variant = g.get("spelling_variant_detected", "UNKNOWN")
        counts = g.get("spelling_variant_counts", {})
        return (
            f"<p>Word count: {g['word_count']} &nbsp;|&nbsp; "
            f"Avg. sentence length: {g['avg_sentence_length']} words &nbsp;|&nbsp; "
            f"NLP backend: {self._esc(g.get('nlp_backend','?'))}</p>"
            f"<p>Spelling variant detected: <strong>{variant}</strong> "
            f"(UK: {counts.get('UK',0)}, US: {counts.get('US',0)}) &nbsp;|&nbsp; "
            f"Quality score: {g['quality_score']:.2f}</p>"
            f"{table}"
        )

    def _guideline_section(self, gc: Optional[dict]) -> str:
        if not gc:
            return ("<p class='no-data'>Guideline compliance was not requested for this "
                    "run (opt-in per venue: IEEE, ACM, BCS, IET, ISACA, Elsevier).</p>")
        cards = []
        for venue, res in gc.items():
            rows = "".join(
                f"<tr><td>{self._esc(c['rule'])}</td>"
                f"<td>{self._status_badge(c['status'])}</td>"
                f"<td>{self._esc(c['detail'])}</td></tr>"
                for c in res.get("checks", [])
            )
            cards.append(
                f"<details open><summary>{self._esc(res['display_name'])} "
                f"{self._status_badge(res['overall_status'])}</summary>"
                f"<p><small>Source: <a href=\"{self._esc(res['source_url'])}\">"
                f"{self._esc(res['source_name'])}</a></small></p>"
                f"<table><thead><tr><th>Rule</th><th>Status</th>"
                f"<th>Detail</th></tr></thead><tbody>{rows}</tbody></table>"
                f"</details>"
            )
        return "".join(cards)

    def _privacy_disclosure(self, network_activity: dict) -> str:
        if not network_activity:
            return (
                "Document content was processed locally and never transmitted anywhere."
            )
        contacted = network_activity.get("external_services_contacted", [])
        if contacted:
            services = self._esc(", ".join(contacted))
            return (
                "Document content was processed locally and never transmitted anywhere. "
                f"Citation metadata (titles, authors, DOIs) was sent to: <strong>{services}</strong> "
                "for online verification."
            )
        return (
            "Document content was processed locally and never transmitted anywhere. "
            "No external services were contacted for this report "
            f"(citation check: {self._esc(network_activity.get('citation_check_mode', 'unknown'))}, "
            f"citation network: {self._esc(network_activity.get('citation_network_mode', 'unknown'))})."
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _esc(text: str) -> str:
        return (str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    @staticmethod
    def _stem(report: AnalysisReport) -> str:
        return Path(report.submission_path).stem.replace(" ", "_")
