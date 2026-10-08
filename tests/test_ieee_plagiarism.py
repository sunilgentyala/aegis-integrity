"""Tests for IEEE PSPB 8.2.4.D plagiarism-level classification."""

from types import SimpleNamespace

from aegis.detectors.ieee_plagiarism import IEEEPlagiarismClassifier
from aegis.detectors.ngram import NGramMatch

COPIED = ("The proposed scheme partitions the input stream into fixed windows "
          "and applies a lightweight hash to every window before transmission "
          "over the constrained channel.")
FILLER = " ".join(f"filler{i}" for i in range(60))


def _m(seg, label="src"):
    return NGramMatch(query_segment=seg, source_label=label, source_segment=seg,
                      jaccard_estimate=0.9, match_type="word_ngram")


def _run(body, matches, sp=None):
    return IEEEPlagiarismClassifier().analyze(body, matches, [], sp, body)


def test_uncredited_small_share_is_level3():
    body = f"{FILLER * 3} {COPIED} {FILLER * 3}"
    r = _run(body, [_m(COPIED)])
    assert r.indicative_level == 3 and r.portion == "significant"
    assert r.risk_level == "MEDIUM"


def test_uncredited_half_is_level1():
    body = f"{COPIED} {FILLER[:40]}"
    r = _run(body, [_m(COPIED)])
    assert r.indicative_level == 1 and r.risk_level == "CRITICAL"


def test_credited_and_quoted_is_not_a_level():
    body = f"{FILLER} \u201c{COPIED}\u201d [4] {FILLER}"
    r = _run(body, [_m(COPIED)])
    assert r.indicative_level is None
    assert r.credited_delineated_pct > 0


def test_credited_without_quotes_flags_but_below_level4_threshold():
    body = f"{FILLER * 4} {COPIED} [4] {FILLER * 4}"
    r = _run(body, [_m(COPIED)])
    assert r.indicative_level is None
    assert r.credited_undelineated_pct > 0
    assert any("without quotation marks" in f for f in r.flags)


def test_credited_undelineated_major_portion_is_level4():
    body = f"{COPIED} [4] ok"
    r = _run(body, [_m(COPIED)])
    assert r.indicative_level == 4


def test_overlapping_matches_not_double_counted():
    body = f"{FILLER * 3} {COPIED} {FILLER * 3}"
    once = _run(body, [_m(COPIED)])
    twice = _run(body, [_m(COPIED, "a"), _m(COPIED, "b")])
    assert twice.uncredited_pct == once.uncredited_pct


def test_undisclosed_self_reuse_flagged():
    sp = SimpleNamespace(overall_overlap_pct=40.0)
    r = _run("Plain text with no disclosure at all.", [], sp)
    assert r.reuse_findings and r.risk_level == "MEDIUM"


def test_disclosed_self_reuse_ok():
    sp = SimpleNamespace(overall_overlap_pct=20.0)
    r = _run("This paper is an extended version of our conference paper.", [], sp)
    assert not r.reuse_findings


def test_borrowed_figure_without_reference_flagged():
    r = _run("Body.\nFig. 2. Architecture, adapted from the vendor manual.\n", [])
    assert r.illustration_findings


def test_clean_text_no_level():
    r = _run("Entirely original prose here.", [])
    assert r.indicative_level is None and r.risk_level == "LOW"


def test_own_prior_work_excluded_from_levels():
    body = f"{FILLER * 3} {COPIED} {FILLER * 3}"
    r = IEEEPlagiarismClassifier().analyze(
        body, [_m(COPIED, "my-2025-paper")], [], None, body,
        own_labels={"my-2025-paper"})
    assert r.indicative_level is None and r.passages == []


def test_credited_undelineated_20pct_raises_medium():
    body = f"{COPIED} [4] {FILLER}"
    r = _run(body, [_m(COPIED)])
    assert r.indicative_level is None and r.credited_undelineated_pct >= 20
    assert r.risk_level == "MEDIUM"
    assert any("approaching" in f for f in r.flags)


def test_citation_at_paragraph_end_credits_a_window_match():
    window = COPIED[:90]
    body = f"{FILLER}\n\n{COPIED} {FILLER[:80]} [7]\n\nNext paragraph."
    r = _run(body, [_m(window)])
    assert r.passages and r.passages[0].kind == "credited_undelineated"


def test_verbatim_semantic_hit_counts_as_copy_not_paraphrase():
    sm = SimpleNamespace(query_sentence=COPIED, source_sentence=COPIED,
                         source_label="s", cosine_score=1.0, is_paraphrase=True)
    body = f"{FILLER * 3} {COPIED} {FILLER * 3}"
    r = IEEEPlagiarismClassifier().analyze(body, [], [sm], None, body)
    assert r.indicative_level == 3 and r.paraphrase_uncredited_pct == 0
