"""
Scientific / Mathematical Formula Checker -- AEGIS v3.0 Novel Feature.

Checks the structural integrity and notation conventions of numbered
equations in a manuscript. This is a compliance/quality signal, not a
misconduct signal: it never affects plagiarism/AI/citation risk scoring
(see AEGISPipeline._assess_overall_risk), and it never claims an equation
is "wrong" -- it flags things a human copy-editor would flag: broken
numbering sequences, dangling or orphaned equation references, malformed
LaTeX math environments, and a handful of formatting conventions that are
explicitly documented in publisher style manuals (cited per-issue via
`rule_source`).

Equation extraction is format-specific because full_text has already had
its math stripped or never had it in the first place:
  - .tex: DocumentParser._clean_latex() deliberately removes
    \\begin{equation}...\\end{equation} (and friends) from full_text, so
    this module re-reads the raw source itself.
  - .docx: python-docx's Paragraph.text never includes OMML (m:oMath)
    equation runs at all -- they are separate XML elements, not text runs
    -- so full_text is silently missing all Word-native equations. This
    module walks the raw document XML for m:oMath elements directly.
  - .pdf / .txt: no equation markup survives text extraction; this module
    falls back to regex heuristics over full_text (numbered-line and
    in-text-reference patterns).
"""

from __future__ import annotations
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_MATH_ENVS = ("equation", "align", "eqnarray", "gather", "multline", "flalign")

# Common countable-plural nouns used to keep the exponential/percentage
# regexes below cheap; not exhaustive, just enough for high-precision hits.
_EXP_NOTATION_RE = re.compile(r"\b\d+(?:\.\d+)?[Ee][+-]?\d{1,3}\b")
_PCT_RANGE_MISSING_SIGN_RE = re.compile(r"\b\d+(?:\.\d+)?\s*[-\u2013\u2014]\s*\d+(?:\.\d+)?%")
_DECIMAL_NO_LEADING_ZERO_RE = re.compile(r"(?<![\w.])\.\d+")
_DOUBLE_PAREN_REF_RE = re.compile(r"\(\s*see\s*\(\d+\)\s*\)", re.IGNORECASE)

_EQ_REF_EXPLICIT_RE = re.compile(
    r"\b(Eq(?:uation)?s?\.?|equations?)\s*\(?\s*(\d{1,3}(?:\.\d{1,3})?)\s*\)?",
    re.IGNORECASE,
)
# Bare "(3)" is only treated as an equation reference when a cue phrase
# immediately precedes it -- a plain "(\d+)" alone false-matches enumerated
# list items ("(1) first step (2) second step"), footnote markers, and
# other parenthesised numbers that have nothing to do with equations, and
# this project's history (see git log: "Fix venue-keyword false-match
# bug", ESL/citation false-positive fixes) treats false-positive flags as
# a correctness bug, not an acceptable tradeoff for recall.
_EQ_REF_CUED_RE = re.compile(
    r"\b(?:in|from|using|via|per|see|cf\.?|solving|substituting|"
    r"given\s+by|shown\s+in|as\s+in|as\s+shown\s+in|combining)\s+"
    r"\(\s*(\d{1,3}(?:\.\d{1,3})?)\s*\)",
    re.IGNORECASE,
)
# Continuation of a cued reference into a list, e.g. "as in (1) and (2)"
# or "(1), (2), and (3)" -- matched only immediately after a cued hit so a
# stray "(2) second step" elsewhere in the text still isn't swept in.
_EQ_REF_CHAIN_RE = re.compile(
    r"\s*(?:,\s*(?:and\s+)?|and\s+|or\s+)\(\s*(\d{1,3}(?:\.\d{1,3})?)\s*\)"
)

# A defined equation: a line ending in a bare parenthesised number, i.e.
# how a rendered/typeset equation number looks once extracted as plain
# text from a PDF ("... = mc^2  (1)").
_EQ_DEFINITION_LINE_RE = re.compile(
    r"^(.*[=<>\u2248\u2264\u2265+\-*/^].{0,200}?)\(\s*(\d{1,3}(?:\.\d{1,3})?)\s*\)\s*$",
    re.MULTILINE,
)

# PDF extraction often puts a display equation's number on its own line,
# after the (possibly multi-line) formula, e.g. "IQR = Q3 - Q1" then "(4)".
# A lone "(N)" line is only taken as an equation number when the line
# before it looks like math -- an operator/symbol, or a short formula
# fragment -- so prose and list items ("(1) Collect the data") are never
# swept in.
_EQ_NUMBER_ONLY_LINE_RE = re.compile(
    r"^[ \t]*\(\s*(\d{1,3}(?:\.\d{1,3})?)\s*\)[ \t]*$", re.MULTILINE)
_MATHY_LINE_RE = re.compile(
    r"[=<>+\-*/^()\[\]|≈≤≥−∑∏∫"
    r"Α-ω∂∇√∈]")


def _previous_nonblank_line(text: str, pos: int) -> str:
    for line in reversed(text[:pos].splitlines()):
        if line.strip():
            return line.strip()
    return ""


@dataclass
class MathIssue:
    category: str          # numbering | reference | notation | malformed_latex
    severity: str           # LOW | MEDIUM
    message: str
    rule_source: str        # which style manual this convention comes from
    location: str = ""      # short excerpt for context


@dataclass
class MathAnalysisResult:
    equations_found: int
    equation_numbers: list[str] = field(default_factory=list)
    numbering_issues: list[MathIssue] = field(default_factory=list)
    reference_issues: list[MathIssue] = field(default_factory=list)
    notation_issues: list[MathIssue] = field(default_factory=list)
    extraction_method: str = "none"   # latex_source | docx_omml | text_heuristic
    limitations: list[str] = field(default_factory=list)

    @property
    def all_issues(self) -> list[MathIssue]:
        return self.numbering_issues + self.reference_issues + self.notation_issues

    @property
    def flags(self) -> list[str]:
        return [f"[Math] {i.message}" for i in self.all_issues if i.severity == "MEDIUM"]


class MathFormulaChecker:
    """Structural + notation checks over a manuscript's numbered equations."""

    def analyze(self, submission_path: str, doc_format: str, full_text: str) -> MathAnalysisResult:
        if doc_format == "latex":
            eq_texts, extraction = self._extract_latex_equations(submission_path), "latex_source"
        elif doc_format == "docx":
            eq_texts, extraction = self._extract_docx_equations(submission_path), "docx_omml"
        else:
            eq_texts, extraction = [], "text_heuristic"

        definitions, numbers_inferred = self._collect_definitions(eq_texts, full_text, doc_format)
        references = self._collect_references(full_text)

        result = MathAnalysisResult(
            equations_found=len(definitions),
            equation_numbers=[d[0] for d in definitions],
            extraction_method=extraction,
        )
        if numbers_inferred:
            result.limitations.append(
                "Equation numbers could not be read from rendered text; equations "
                "were assumed to be numbered sequentially in source order, so "
                "numbering-sequence checks will not catch an actual renumbering error."
            )

        result.numbering_issues = [] if numbers_inferred else self._check_numbering(definitions)
        result.reference_issues = self._check_references(definitions, references)
        result.notation_issues = self._check_notation(full_text, eq_texts, doc_format)

        if doc_format in ("pdf", "txt", "bib"):
            result.limitations.append(
                "Equations were located via text-pattern heuristics, not native math "
                "markup -- numbering/reference checks are best-effort and may miss "
                "equations that a PDF extractor rendered without a clean trailing "
                "number, or equations delivered as images."
            )
        if doc_format == "docx" and not eq_texts:
            result.limitations.append(
                "No native Word equation objects (OMML) were found. Equations inserted "
                "as pictures or legacy MathType OLE objects are not detected."
            )
        return result

    # ------------------------------------------------------------------
    # Equation extraction
    # ------------------------------------------------------------------

    def _extract_latex_equations(self, path: str) -> list[str]:
        try:
            raw = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        pattern = re.compile(
            r"\\begin\{(" + "|".join(_MATH_ENVS) + r")\*?\}(.*?)\\end\{\1\*?\}",
            re.DOTALL,
        )
        return [m.group(2).strip() for m in pattern.finditer(raw)]

    def _extract_docx_equations(self, path: str) -> list[str]:
        """Walk the raw document.xml for m:oMath elements. python-docx has
        no public API for OMML, so this reads the zip part directly."""
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        except (OSError, KeyError, zipfile.BadZipFile):
            return []
        blocks = re.findall(r"<m:oMath\b[^>]*>(.*?)</m:oMath>", xml, re.DOTALL)
        equations = []
        for block in blocks:
            texts = re.findall(r"<m:t[^>]*>(.*?)</m:t>", block, re.DOTALL)
            joined = "".join(texts).strip()
            if joined:
                equations.append(joined)
        return equations

    # ------------------------------------------------------------------
    # Numbering / reference collection
    # ------------------------------------------------------------------

    def _collect_definitions(
        self, eq_texts: list[str], full_text: str, doc_format: str
    ) -> tuple[list[tuple[str, str]], bool]:
        """Returns ([(number, raw_text), ...], numbers_were_inferred).

        Numbers are read from a trailing rendered number in full_text
        where one survived extraction (true for PDF/DOCX after Word/LaTeX
        typesets the document); when equations were extracted from
        un-compiled LaTeX source instead, no rendered number exists yet,
        so equations are numbered sequentially by appearance and the
        caller is told this is inferred, not verified."""
        found = [(m.start(), m.group(2), m.group(1).strip())
                 for m in _EQ_DEFINITION_LINE_RE.finditer(full_text)]
        for m in _EQ_NUMBER_ONLY_LINE_RE.finditer(full_text):
            prev = _previous_nonblank_line(full_text, m.start())
            if prev and (_MATHY_LINE_RE.search(prev) or len(prev) <= 40):
                found.append((m.start(), m.group(1), prev))
        if found:
            found.sort(key=lambda f: f[0])
            return [(num, expr) for _, num, expr in found], False
        if eq_texts:
            return [(str(i + 1), t) for i, t in enumerate(eq_texts)], True
        return [], False

    def _collect_references(self, full_text: str) -> list[tuple[str, str]]:
        """Returns [(number, phrasing), ...] for every in-text equation
        reference, e.g. ("3", "Eq.") or ("5", "cued")."""
        refs = []
        for m in _EQ_REF_EXPLICIT_RE.finditer(full_text):
            phrasing = re.sub(r"s$", "", m.group(1).rstrip(".")).title()
            refs.append((m.group(2), phrasing))
        for m in _EQ_REF_CUED_RE.finditer(full_text):
            refs.append((m.group(1), "cued"))
            pos = m.end()
            while True:
                chain = _EQ_REF_CHAIN_RE.match(full_text, pos)
                if not chain:
                    break
                refs.append((chain.group(1), "cued"))
                pos = chain.end()
        return refs

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_numbering(self, definitions: list[tuple[str, str]]) -> list[MathIssue]:
        issues: list[MathIssue] = []
        if not definitions:
            return issues
        nums = []
        for n, _ in definitions:
            try:
                nums.append(int(float(n)))
            except ValueError:
                continue
        if not nums:
            return issues

        seen = set()
        dupes = set()
        for n in nums:
            (dupes if n in seen else seen).add(n)
        if dupes:
            issues.append(MathIssue(
                category="numbering", severity="MEDIUM",
                message=f"Duplicate equation number(s) found: {sorted(dupes)}.",
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.24: "
                            "\"should not have repeats or missing numbers\"",
            ))

        expected = list(range(min(nums), max(nums) + 1))
        missing = sorted(set(expected) - set(nums))
        if missing:
            issues.append(MathIssue(
                category="numbering", severity="LOW",
                message=f"Possible gap in equation numbering: {missing} not found "
                        f"between ({min(nums)}) and ({max(nums)}).",
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.24",
            ))

        if nums != sorted(nums):
            issues.append(MathIssue(
                category="numbering", severity="LOW",
                message="Equation numbers do not appear in strictly increasing order "
                        "through the document.",
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.24: "
                            "\"numbering should be consecutive\"",
            ))
        return issues

    def _check_references(
        self, definitions: list[tuple[str, str]], references: list[tuple[str, str]]
    ) -> list[MathIssue]:
        issues: list[MathIssue] = []
        if not definitions:
            return issues
        defined = {n for n, _ in definitions}

        dangling = sorted({n for n, _ in references if n not in defined and "." not in n},
                           key=lambda x: int(x))
        if dangling:
            issues.append(MathIssue(
                category="reference", severity="MEDIUM",
                message=f"In-text reference(s) to equation number(s) {dangling} do not "
                        f"match any numbered equation found in the document -- possible "
                        f"renumbering error or a reference left over from an earlier draft.",
                rule_source="general manuscript-consistency check",
            ))

        referenced = {n for n, _ in references}
        orphans = sorted({n for n in defined if n not in referenced}, key=lambda x: int(x) if x.isdigit() else 0)
        if orphans and len(orphans) < len(defined):
            issues.append(MathIssue(
                category="reference", severity="LOW",
                message=f"Equation(s) {orphans} are numbered but never referenced "
                        f"elsewhere in the text. Not necessarily an error -- some "
                        f"equations (e.g. a final result) are left to stand alone.",
                rule_source="general manuscript-consistency check",
            ))

        phrasings = {p for _, p in references if p != "cued"}
        if len(phrasings) > 1:
            issues.append(MathIssue(
                category="reference", severity="LOW",
                message=f"Equation references use inconsistent phrasing across the "
                        f"document: {sorted(phrasings)}. Pick one convention "
                        f"(e.g. always \"(n)\" or always \"Eq. (n)\") and use it "
                        f"throughout.",
                rule_source="general house-style consistency",
            ))
        return issues

    def _check_notation(
        self, full_text: str, eq_texts: list[str], doc_format: str
    ) -> list[MathIssue]:
        issues: list[MathIssue] = []
        search_space = "\n".join(eq_texts) if eq_texts else full_text

        if _EXP_NOTATION_RE.search(search_space):
            n = len(_EXP_NOTATION_RE.findall(search_space))
            issues.append(MathIssue(
                category="notation", severity="LOW",
                message=f"{n} value(s) written in raw exponential notation "
                        f"(e.g. \"5E03\") rather than scientific notation.",
                rule_source="IET Research Journals Author Guide: \"Exponential "
                            "expressions should be written using superscript "
                            "notation (e.g., 5x10\u00b3 not 5E03)\"",
            ))

        pct_matches = _PCT_RANGE_MISSING_SIGN_RE.findall(full_text)
        if pct_matches:
            issues.append(MathIssue(
                category="notation", severity="LOW",
                message=f"{len(pct_matches)} percentage range(s) omit the % sign on "
                        f"the first number (e.g. \"20-30%\" instead of \"20%-30%\").",
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.23: "
                            "\"the percentage symbol is repeated in lists and ranges\"",
            ))

        decimal_matches = _DECIMAL_NO_LEADING_ZERO_RE.findall(full_text)
        if decimal_matches:
            issues.append(MathIssue(
                category="notation", severity="LOW",
                message=f"{len(decimal_matches)} decimal value(s) written without a "
                        f"leading zero (e.g. \".25\" instead of \"0.25\").",
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.23: "
                            "\"Always add a zero before decimals\"",
            ))

        if _DOUBLE_PAREN_REF_RE.search(full_text):
            issues.append(MathIssue(
                category="notation", severity="LOW",
                message="Found a doubly-parenthesised equation reference "
                        "(e.g. \"(see (10))\"); IEEE style uses brackets for the "
                        "outer reference: \"[see (10)]\".",
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.26",
            ))

        if doc_format == "latex":
            issues.extend(self._check_latex_balance(eq_texts))
        return issues

    def _check_latex_balance(self, eq_texts: list[str]) -> list[MathIssue]:
        issues: list[MathIssue] = []
        malformed = 0
        for eq in eq_texts:
            if eq.count("{") != eq.count("}"):
                malformed += 1
        if malformed:
            issues.append(MathIssue(
                category="malformed_latex", severity="MEDIUM",
                message=f"{malformed} equation environment(s) have unbalanced "
                        f"braces ({{ }}), which will fail to compile or render "
                        f"incorrectly.",
                rule_source="LaTeX syntax",
            ))
        return issues
