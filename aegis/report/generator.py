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
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _report_to_dict(self, r: AnalysisReport) -> dict:
        d: dict = {
            "aegis_version": "2.1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "submission": r.submission_path,
            "elapsed_seconds": r.elapsed_seconds,
            "overall_risk": r.overall_risk,
            "flags": r.flags,
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
                    }
                    for p in ai.paragraph_scores
                ],
            }

        # Citation integrity
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

        ngram_rows = self._ngram_table_rows(data.get("ngram_matches", []))
        semantic_rows = self._semantic_table_rows(data.get("semantic_matches", []))
        citation_rows = self._citation_table_rows(data.get("citation_integrity", []))
        ai_section = self._ai_section(data.get("ai_detection"))
        stylo_section = self._stylo_section(data.get("stylometric"))
        self_plag_section = self._self_plag_section(data.get("self_plagiarism"))
        watermark_section = self._watermark_section(data.get("watermark"))

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

  <!-- Stylometric -->
  <h2>Stylometric Analysis (Authorship Consistency)</h2>
  <div class="section">{stylo_section}</div>

  <!-- Self-plagiarism -->
  <h2>Self-Plagiarism / Text Recycling</h2>
  <div class="section">{self_plag_section}</div>

  <!-- Watermark analysis -->
  <h2>LLM Watermark Analysis</h2>
  <div class="section">{watermark_section}</div>

  <footer>AEGIS Academic Integrity Tool v2.1.0 &mdash;
  Open-source, no data transmitted to third parties</footer>
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
            f"{k}: {v}%" for k, v in sp.get("source_breakdown", {}).items()
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
            + "".join(f"<li>{self._esc(l)}</li>" for l in wm.get("limitations", []))
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
