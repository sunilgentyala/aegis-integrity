"""Markdown prose should exclude metadata and fenced code."""
import pytest

from aegis.core.document import DocumentParser


@pytest.mark.parametrize("suffix", [".md", ".MD"])
def test_markdown_strips_metadata_and_code_but_keeps_headings(tmp_path, suffix):
    path = tmp_path / ("paper" + suffix)
    path.write_text("---\ntitle: Metadata\n---\n# Paper title\n\n## Abstract\nA short abstract.\n\n## Introduction\nProse before.\n\n```python\nnot prose\n```\n\nProse after.\n", encoding="utf-8")
    doc = DocumentParser().parse(path)
    assert doc.format == "markdown"
    assert "Metadata" not in doc.full_text
    assert "not prose" not in doc.full_text
    assert "Paper title" in doc.full_text
    assert "Introduction" in doc.full_text
    assert "Prose before." in doc.full_text and "Prose after." in doc.full_text
    assert doc.abstract == "A short abstract."


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_fence_requires_matching_character_and_length(tmp_path, fence):
    path = tmp_path / "paper.md"
    other = "~~~" if fence[0] == "`" else "```"
    path.write_text(f"Before.\n\n{fence}\nhidden\n{other}\nstill hidden\n{fence[0] * 2}\nhidden too\n{fence}\n\nAfter.\n")
    doc = DocumentParser().parse(path)
    assert "hidden" not in doc.full_text
    assert "Before." in doc.full_text and "After." in doc.full_text


def test_unclosed_fence_discards_code_to_end(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("Prose.\n```\ncode\n")
    assert DocumentParser().parse(path).full_text == "Prose.\n"


def test_plain_text_keeps_markdown_syntax(tmp_path):
    path = tmp_path / "paper.txt"
    text = "---\nmetadata\n---\n```\ntext\n```\n"
    path.write_text(text)
    doc = DocumentParser().parse(path)
    assert doc.format == "txt"
    assert doc.full_text == text


def test_thematic_break_does_not_strip_prose(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("Before.\n---\nAfter.\n")
    assert "Before." in DocumentParser().parse(path).full_text
    assert "After." in DocumentParser().parse(path).full_text


def test_cli_directory_collection_includes_markdown(tmp_path):
    from aegis.cli import _collect_docs
    (tmp_path / "paper.md").write_text("# Title\n\nProse.\n```\ncode\n```\n")
    assert _collect_docs([str(tmp_path)]) == [("paper", "Title\n\nProse.\n")]


def test_front_matter_alternate_terminator_and_closed_heading(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("---\nauthor: Hidden\n...\n## Abstract ##\nSummary.\n\nBody.\n")
    doc = DocumentParser().parse(path)
    assert "Hidden" not in doc.full_text
    assert doc.abstract == "Summary."


def test_unterminated_front_matter_preserves_text(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("---\nText without a closing delimiter.\n")
    assert "Text without" in DocumentParser().parse(path).full_text


def test_markdown_math_discloses_plain_text_limitations(tmp_path):
    from aegis.detectors.math_formula import MathFormulaChecker
    path = tmp_path / "paper.md"
    path.write_text("# Results\nE = mc^2 (1)\n")
    doc = DocumentParser().parse(path)
    result = MathFormulaChecker().analyze(str(path), doc.format, doc.full_text)
    assert result.equation_numbers == ["1"]
    assert any("text-pattern heuristics" in limitation for limitation in result.limitations)
