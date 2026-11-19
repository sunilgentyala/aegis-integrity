"""
Grammar & Language Convention Checker -- AEGIS v3.0 Novel Feature.

A rule-based English grammar/usage/style checker for academic manuscript
bodies. This deliberately does NOT require an external grammar service or
a Java runtime (unlike e.g. LanguageTool): every check here is a plain
regex or spaCy POS heuristic that runs fully offline, in-process, with no
new hard dependency -- spaCy is already an AEGIS dependency (see
aegis.core.preprocessor.Preprocessor, which this module mirrors: try to
load en_core_web_sm, fall back to regex-only checks if it isn't
installed).

Like MathFormulaChecker, this is a compliance/quality signal, not a
misconduct signal, and never affects plagiarism/AI/citation risk scoring.
Every check cites the convention it is based on so a human can verify the
rule rather than take the tool's word for it. Stylometric authorship
signals (passive-voice ratio, hedge density, readability, TTR) already
live in aegis.detectors.stylometric.StylometricAnalyzer and are not
duplicated here; this module focuses on mechanical grammar/usage
correctness and US/UK spelling consistency instead.
"""

from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

_CONTRACTIONS_RE = re.compile(
    r"\b(don't|doesn't|didn't|can't|won't|wouldn't|shouldn't|"
    r"couldn't|isn't|aren't|wasn't|weren't|hasn't|haven't|hadn't|"
    r"it's|that's|there's|here's|let's|what's|who's|"
    r"i'm|we're|they're|you're|he's|she's|"
    r"i've|we've|they've|you've|"
    r"i'll|we'll|they'll|you'll|he'll|she'll)\b",
    re.IGNORECASE,
)
# IEEE Editorial Style Manual for Authors (2024), p.22: contractions are
# disallowed in technical text except these idiomatic engineering terms.
_CONTRACTION_EXCEPTIONS = {"don't-care", "don't care"}

# (UK, US) spelling pairs. Not exhaustive -- large enough to detect a
# document that mixes conventions, which is the actual signal of interest;
# a document consistently using one variant throughout is not flagged.
_UK_US_PAIRS = [
    ("behaviour", "behavior"), ("colour", "color"), ("favour", "favor"),
    ("honour", "honor"), ("labour", "labor"), ("neighbour", "neighbor"),
    ("rumour", "rumor"), ("vapour", "vapor"),
    ("centre", "center"), ("metre", "meter"), ("theatre", "theater"),
    ("fibre", "fiber"), ("litre", "liter"),
    ("organisation", "organization"), ("organise", "organize"),
    ("organised", "organized"), ("organising", "organizing"),
    ("analyse", "analyze"), ("analysed", "analyzed"), ("analysing", "analyzing"),
    ("recognise", "recognize"), ("recognised", "recognized"),
    ("optimise", "optimize"), ("optimised", "optimized"), ("optimisation", "optimization"),
    ("characterise", "characterize"), ("characterised", "characterized"),
    ("minimise", "minimize"), ("maximise", "maximize"),
    ("catalogue", "catalog"), ("dialogue", "dialog"),
    ("programme", "program"),
    ("defence", "defense"), ("licence", "license"), ("practise", "practice"),
    ("modelling", "modeling"), ("modelled", "modeled"),
    ("cancelled", "canceled"), ("cancelling", "canceling"),
    ("travelled", "traveled"), ("travelling", "traveling"),
    ("labelled", "labeled"), ("labelling", "labeling"),
    ("signalling", "signaling"), ("signalled", "signaled"),
    ("judgement", "judgment"), ("acknowledgement", "acknowledgment"),
    ("polarisation", "polarization"), ("utilise", "utilize"), ("utilised", "utilized"),
    ("realise", "realize"), ("realised", "realized"),
    ("emphasise", "emphasize"), ("emphasised", "emphasized"),
    ("categorise", "categorize"), ("categorised", "categorized"),
    ("prioritise", "prioritize"), ("prioritised", "prioritized"),
    ("summarise", "summarize"), ("summarised", "summarized"),
]

_DECADE_APOSTROPHE_RE = re.compile(r"\b((?:19|20)\d0)'s\b")
_ACRONYM_PLURAL_APOSTROPHE_RE = re.compile(r"\b([A-Z]{2,6})'s\s+(?:are|were)\b")
_REPEATED_WORD_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
# A sentence that opens with a numeral ("12 participants were recruited.") should
# spell the number out or be reworded. Matched only at the very start of the text
# or right after sentence-ending punctuation, so numbered headings ("1 Introduction")
# and list markers on their own lines are not touched. Years ("2024 was ...") are
# common enough in technical prose that they are excluded.
_SENTENCE_INITIAL_NUMERAL_RE = re.compile(
    r"(?:\A\s*|(?<=[.!?])[ \t]+)(?!(?:19|20)\d{2}\b)(\d+(?:[.,]\d+)?[ \t]+[A-Za-z][^.!?\n]{0,60})"
)
_COMPRISED_OF_RE = re.compile(r"\bcomprised of\b", re.IGNORECASE)
_A_LOT_RE = re.compile(r"\balot\b", re.IGNORECASE)
_IRREGARDLESS_RE = re.compile(r"\birregardless\b", re.IGNORECASE)
_MODAL_OF_RE = re.compile(r"\b(could|would|should|might|must)\s+of\b", re.IGNORECASE)
_COMPARATIVE_THEN_RE = re.compile(
    r"\b(more|less|other|rather|greater|higher|lower|fewer|better|worse)\s+then\b",
    re.IGNORECASE,
)
_ITS_DOUBLE_APOSTROPHE_RE = re.compile(r"\bits'\b", re.IGNORECASE)

_DATA_SINGULAR_RE = re.compile(r"\bdata\s+(is|was|has)\b", re.IGNORECASE)
_A_NUMBER_OF_SINGULAR_RE = re.compile(r"\ba number of\b[^.;]{0,60}?\b(is|was|has)\b", re.IGNORECASE)
_THE_NUMBER_OF_PLURAL_RE = re.compile(r"\bthe number of\b[^.;]{0,60}?\b(are|were|have)\b", re.IGNORECASE)
_A_SERIES_OF_PLURAL_RE = re.compile(r"\ba series of\b[^.;]{0,60}?\b(are|were)\b", re.IGNORECASE)

_COUNTABLE_NOUNS = (
    "samples", "users", "nodes", "papers", "studies", "participants", "errors",
    "tests", "iterations", "parameters", "features", "methods", "datasets",
    "records", "files", "packets", "requests", "devices", "citations",
    "references", "experiments", "trials", "epochs", "queries", "clients",
    "attacks", "vulnerabilities", "instances", "cases", "models",
)
_LESS_PLUS_COUNTABLE_RE = re.compile(
    r"\bless\s+(" + "|".join(_COUNTABLE_NOUNS) + r")\b", re.IGNORECASE
)

_UNCOMMA_WHICH_RE = re.compile(r"\b\w+\s+which\b(?!\s*,)")

_LIST_LINE_RE = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+", re.MULTILINE)

_FIRST_PERSON_SINGULAR_RE = re.compile(r"\bI\b")
_SECOND_PERSON_RE = re.compile(r"\b(you|your|you're)\b", re.IGNORECASE)


@dataclass
class GrammarIssue:
    category: str        # contraction | spelling_mix | agreement | usage | style
    severity: str          # LOW | MEDIUM
    message: str
    count: int
    examples: list[str] = field(default_factory=list)
    rule_source: str = "general English usage"


@dataclass
class GrammarAnalysisResult:
    word_count: int
    sentence_count: int
    avg_sentence_length: float
    long_sentence_count: int
    spelling_variant_detected: str        # US | UK | MIXED | UNKNOWN
    spelling_variant_counts: dict         # {"UK": n, "US": n}
    contraction_count: int
    first_person_singular_count: int      # "I" occurrences
    second_person_count: int              # "you"/"your" occurrences
    list_line_count: int
    paragraph_count: int
    issues: list[GrammarIssue] = field(default_factory=list)
    quality_score: float = 1.0            # 1.0 = no mechanical issues found
    nlp_backend: str = "regex_only"       # regex_only | spacy

    @property
    def flags(self) -> list[str]:
        return [f"[Grammar] {i.message}" for i in self.issues if i.severity == "MEDIUM"]


class GrammarLanguageChecker:
    """Offline, dependency-light grammar/usage/spelling-consistency checks."""

    def __init__(self, use_spacy: bool = True, long_sentence_words: int = 45):
        self.long_sentence_words = long_sentence_words
        self._nlp = None
        if use_spacy:
            try:
                import spacy
                self._nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
            except (ImportError, OSError):
                logger.debug("spaCy model unavailable; grammar checks run regex-only.")

    def analyze(self, text: str) -> GrammarAnalysisResult:
        text = text or ""
        words = re.findall(r"[A-Za-z']+", text)
        word_count = len(words)
        sentences = self._split_sentences(text)
        sentence_lengths = [len(s.split()) for s in sentences]
        avg_len = round(sum(sentence_lengths) / len(sentence_lengths), 1) if sentence_lengths else 0.0
        long_sentences = [s for s, n in zip(sentences, sentence_lengths) if n > self.long_sentence_words]
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]

        issues: list[GrammarIssue] = []

        uk_count, us_count, mixed_examples = self._spelling_variant_counts(text)
        variant = self._classify_variant(uk_count, us_count)
        if variant == "MIXED":
            issues.append(GrammarIssue(
                category="spelling_mix", severity="MEDIUM",
                message=f"Document mixes British and American spelling "
                        f"(UK-style: {uk_count} occurrence(s), US-style: {us_count}). "
                        f"Pick one convention and use it consistently.",
                count=uk_count + us_count, examples=mixed_examples[:6],
                rule_source="general house-style consistency",
            ))

        contractions = _CONTRACTIONS_RE.findall(text)
        contraction_count = self._count_excluding_exceptions(text, contractions)
        if contraction_count:
            issues.append(GrammarIssue(
                category="contraction", severity="LOW",
                message=f"{contraction_count} contraction(s) found (e.g. \"don't\", "
                        f"\"it's\") -- contractions are conventionally avoided in "
                        f"formal technical writing.",
                count=contraction_count,
                examples=self._examples(_CONTRACTIONS_RE, text),
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.22: "
                            "\"Contractions such as 'don't' and 'can't' are not used "
                            "in technical text\"",
            ))

        issues.extend(self._agreement_issues(text))
        issues.extend(self._usage_issues(text))

        if long_sentences:
            issues.append(GrammarIssue(
                category="style", severity="LOW",
                message=f"{len(long_sentences)} sentence(s) exceed "
                        f"{self.long_sentence_words} words; consider splitting for "
                        f"readability.",
                count=len(long_sentences),
                examples=[s[:160] for s in long_sentences[:3]],
                rule_source="general readability guidance",
            ))

        decade_hits = _DECADE_APOSTROPHE_RE.findall(text)
        if decade_hits:
            issues.append(GrammarIssue(
                category="usage", severity="LOW",
                message=f"{len(decade_hits)} decade written with an apostrophe "
                        f"(e.g. \"1990's\"); the plural of a year takes no "
                        f"apostrophe: \"1990s\".",
                count=len(decade_hits), examples=[f"{d}'s" for d in decade_hits[:5]],
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.21: "
                            "\"The plural of calendar years do not take the "
                            "apostrophe before the 's'\"",
            ))

        acronym_hits = _ACRONYM_PLURAL_APOSTROPHE_RE.findall(text)
        if acronym_hits:
            issues.append(GrammarIssue(
                category="usage", severity="LOW",
                message=f"{len(acronym_hits)} acronym plural written with an "
                        f"apostrophe (e.g. \"FET's are\"); acronym plurals take no "
                        f"apostrophe: \"FETs\".",
                count=len(acronym_hits), examples=acronym_hits[:5],
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.26: "
                            "\"All acronyms and numerical plurals do not use "
                            "apostrophes\"",
            ))

        repeated = _REPEATED_WORD_RE.findall(text)
        if repeated:
            issues.append(GrammarIssue(
                category="usage", severity="LOW",
                message=f"{len(repeated)} immediately-repeated word(s) found "
                        f"(e.g. \"the the\").",
                count=len(repeated), examples=list(dict.fromkeys(repeated))[:5],
                rule_source="general proofreading check",
            ))

        numeral_starts = _SENTENCE_INITIAL_NUMERAL_RE.findall(text)
        if numeral_starts:
            issues.append(GrammarIssue(
                category="usage", severity="LOW",
                message=f"{len(numeral_starts)} sentence(s) begin with a numeral "
                        f"(e.g. \"12 participants were ...\"); spell the number out "
                        f"or reword the sentence.",
                count=len(numeral_starts),
                examples=[n.strip() for n in numeral_starts[:5]],
                rule_source="general style convention: do not begin a sentence "
                            "with a numeral",
            ))

        list_lines = len(_LIST_LINE_RE.findall(text))

        result = GrammarAnalysisResult(
            word_count=word_count,
            sentence_count=len(sentences),
            avg_sentence_length=avg_len,
            long_sentence_count=len(long_sentences),
            spelling_variant_detected=variant,
            spelling_variant_counts={"UK": uk_count, "US": us_count},
            contraction_count=contraction_count,
            first_person_singular_count=len(_FIRST_PERSON_SINGULAR_RE.findall(text)),
            second_person_count=len(_SECOND_PERSON_RE.findall(text)),
            list_line_count=list_lines,
            paragraph_count=len(paragraphs),
            issues=issues,
            nlp_backend="spacy" if self._nlp else "regex_only",
        )
        result.quality_score = self._quality_score(issues, word_count)
        return result

    # ------------------------------------------------------------------

    def _split_sentences(self, text: str) -> list[str]:
        if self._nlp:
            try:
                doc = self._nlp(text)
                return [s.text.strip() for s in doc.sents if len(s.text.strip()) > 5]
            except Exception as exc:  # pragma: no cover -- defensive
                logger.debug("spaCy sentence split failed, falling back: %s", exc)
        protected = re.sub(
            r"\b(e\.g|i\.e|et al|Fig|Eq|cf|vs|Dr|Mr|Mrs|Prof)\.",
            lambda m: m.group(0).replace(".", "<DOT>"), text,
        )
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", protected)
        return [p.replace("<DOT>", ".").strip() for p in parts if len(p.strip()) > 5]

    def _spelling_variant_counts(self, text: str) -> tuple[int, int, list[str]]:
        text_lower = text.lower()
        uk_total = us_total = 0
        examples = []
        for uk, us in _UK_US_PAIRS:
            uk_n = len(re.findall(r"\b" + re.escape(uk) + r"\b", text_lower))
            us_n = len(re.findall(r"\b" + re.escape(us) + r"\b", text_lower))
            if uk_n:
                uk_total += uk_n
                examples.append(uk)
            if us_n:
                us_total += us_n
                examples.append(us)
        return uk_total, us_total, examples

    def _classify_variant(self, uk_count: int, us_count: int) -> str:
        if uk_count == 0 and us_count == 0:
            return "UNKNOWN"
        if uk_count > 0 and us_count > 0:
            return "MIXED"
        return "UK" if uk_count > us_count else "US"

    def _count_excluding_exceptions(self, text: str, raw_matches: list[str]) -> int:
        count = len(raw_matches)
        for exc in _CONTRACTION_EXCEPTIONS:
            count -= len(re.findall(re.escape(exc), text, re.IGNORECASE))
        return max(0, count)

    def _examples(self, pattern: re.Pattern, text: str, limit: int = 5) -> list[str]:
        seen = []
        for m in pattern.finditer(text):
            start = max(0, m.start() - 20)
            snippet = text[start:m.end() + 20].strip()
            if snippet not in seen:
                seen.append(snippet)
            if len(seen) >= limit:
                break
        return seen

    def _agreement_issues(self, text: str) -> list[GrammarIssue]:
        issues = []
        checks = [
            (_DATA_SINGULAR_RE, "\"data\" is conventionally treated as plural in "
             "formal technical writing (\"the data are\", not \"the data is\")."),
            (_A_NUMBER_OF_SINGULAR_RE, "\"a number of X\" takes a plural verb "
             "(\"a number of samples were collected\")."),
            (_THE_NUMBER_OF_PLURAL_RE, "\"the number of X\" takes a singular verb "
             "(\"the number of samples was recorded\")."),
            (_A_SERIES_OF_PLURAL_RE, "\"a series of X\" takes a singular verb "
             "(\"a series of tests was run\")."),
        ]
        for pattern, explanation in checks:
            hits = pattern.findall(text)
            if hits:
                issues.append(GrammarIssue(
                    category="agreement", severity="LOW",
                    message=f"{len(hits)} possible subject/verb agreement issue(s): "
                            f"{explanation}",
                    count=len(hits), examples=self._examples(pattern, text, 3),
                    rule_source="IEEE Editorial Style Manual for Authors (2024), p.22 "
                                "(Grammar: Number/Data/Series/Quantity)",
                ))
        return issues

    def _usage_issues(self, text: str) -> list[GrammarIssue]:
        issues = []
        usage_checks = [
            (_COMPRISED_OF_RE, "\"comprised of\" is nonstandard; use \"comprises\" "
             "or \"is composed of\".", "general usage"),
            (_A_LOT_RE, "\"alot\" is not a word; use \"a lot\".", "spelling"),
            (_IRREGARDLESS_RE, "\"irregardless\" is nonstandard; use \"regardless\".",
             "usage"),
            (_MODAL_OF_RE, "modal + \"of\" (e.g. \"could of\") should be modal + "
             "\"have\" (\"could have\").", "usage"),
            (_COMPARATIVE_THEN_RE, "comparative + \"then\" should be comparative + "
             "\"than\" (e.g. \"greater than\", not \"greater then\").", "usage"),
            (_ITS_DOUBLE_APOSTROPHE_RE, "\"its'\" is never correct; use \"its\" "
             "(possessive) or \"it's\" (it is).", "usage"),
            (_LESS_PLUS_COUNTABLE_RE, "\"less\" modifies mass nouns; countable "
             "plural nouns take \"fewer\" (e.g. \"fewer samples\", not \"less "
             "samples\").", "usage"),
        ]
        for pattern, explanation, _tag in usage_checks:
            hits = pattern.findall(text)
            if hits:
                issues.append(GrammarIssue(
                    category="usage", severity="LOW",
                    message=f"{len(hits)} instance(s): {explanation}",
                    count=len(hits), examples=self._examples(pattern, text, 3),
                ))

        which_hits = _UNCOMMA_WHICH_RE.findall(text)
        if which_hits:
            issues.append(GrammarIssue(
                category="usage", severity="LOW",
                message=f"{len(which_hits)} use(s) of \"which\" with no preceding "
                        f"comma; if the clause is restrictive, \"that\" is "
                        f"conventionally preferred. (Advisory -- not always wrong.)",
                count=len(which_hits), examples=self._examples(_UNCOMMA_WHICH_RE, text, 3),
                rule_source="IEEE Editorial Style Manual for Authors (2024), p.27 "
                            "(Words Often Confused: that/which)",
            ))
        return issues

    def _quality_score(self, issues: list[GrammarIssue], word_count: int) -> float:
        if word_count == 0:
            return 1.0
        weight = {"LOW": 1, "MEDIUM": 2}
        total = sum(weight.get(i.severity, 1) * i.count for i in issues)
        per_1000 = total / (word_count / 1000)
        return round(max(0.0, 1.0 - min(1.0, per_1000 / 25)), 3)
