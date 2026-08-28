"""Memory extraction.

Turns ingested chunks into durable, reusable memories - not a copy of every
sentence. The default extractor is deterministic and offline so ingestion works
(and is testable) with no model provider configured; a model-backed extractor
plugs in behind the same interface.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.config import get_settings

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n")
_WHITESPACE_RE = re.compile(r"\s+")
_CODEISH_RE = re.compile(r"[{};=<>|]{2,}|^\s*(def |class |import |from |function |const |let |var )")
# A markdown table row: starts with a pipe, or carries two or more cell
# separators. Table cells read as prose to the rules below but carry none of
# the meaning, and a documentation-heavy corpus is mostly tables.
_TABLE_ROW_RE = re.compile(r"^\s*\|| \| .* \| ")
# A sentence that begins mid-clause is a fragment left by chunk splitting.
_FRAGMENT_START_RE = re.compile(r"^[a-z0-9]")
# ...and one that *ends* on a word that cannot end a sentence is truncated.
_TRUNCATED_END_RE = re.compile(
    r"\b(?:a|an|the|and|or|but|of|to|in|on|for|with|that|which|is|was|are|were|be|been|"
    r"can|can't|cannot|will|would|should|must|may|might|as|at|by|from|into|than|then)\s*[\-\u2014,]*\s*$",
    re.IGNORECASE,
)
MIN_SENTENCE_WORDS = 5

MIN_SENTENCE_CHARS = 25
MAX_SENTENCE_CHARS = 400


@dataclass
class ExtractedMemory:
    type: str
    content: str
    confidence: float
    importance: float
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Rule:
    type: str
    patterns: tuple[str, ...]
    base_confidence: float
    base_importance: float


# Ordered most specific first; the first rule that matches wins, so "we decided
# the service must ..." is recorded as a decision rather than a constraint.
RULES: tuple[Rule, ...] = (
    Rule(
        "decision",
        (
            r"\bwe (?:decided|chose|agreed|settled on|are going with|will use|opted)\b",
            r"\bdecision\s*:",
            r"\bit was (?:decided|agreed)\b",
            r"\bwe(?:'ll| will) (?:ship|build|adopt|standardi[sz]e)\b",
        ),
        0.85,
        0.8,
    ),
    Rule(
        "lesson",
        (
            r"\bwe learned\b",
            r"\blesson(?:s)? learned\b",
            r"\bnext time\b",
            r"\bin hindsight\b",
            r"\b(?:previous|last|earlier) attempt\b",
            r"\bthis (?:did not|didn't) work\b",
        ),
        0.8,
        0.75,
    ),
    Rule(
        "gotcha",
        (
            r"\bgotcha\b",
            r"\bwatch out\b",
            r"\bbe careful\b",
            r"\bbeware\b",
            r"\beasy to (?:miss|forget)\b",
            r"\bcounter-?intuitiv",
            r"\bdon'?t forget\b",
        ),
        0.75,
        0.7,
    ),
    Rule(
        "risk",
        (
            r"\brisk(?:s|y)?\b",
            r"\bcould (?:fail|break|corrupt|leak)\b",
            r"\boutage\b",
            r"\bdata loss\b",
            r"\bvulnerab",
            r"\bsecurity (?:issue|concern|hole)\b",
            r"\bregression\b",
        ),
        0.75,
        0.85,
    ),
    Rule(
        "constraint",
        (
            r"\bmust (?:not )?\b",
            r"\bcannot\b|\bcan'?t\b",
            r"\bmay not\b",
            r"\bis required to\b|\bare required to\b",
            r"\bno more than\b|\bat most\b|\bat least\b",
            r"\bonly (?:if|when|after)\b",
            r"\blimited to\b|\blimit of\b",
            r"\bnever\b",
        ),
        0.75,
        0.75,
    ),
    Rule(
        "open_question",
        (
            r"\?\s*$",
            r"\btbd\b",
            r"\bopen question\b",
            r"\bstill (?:unclear|undecided|unknown)\b",
            r"\bneeds? a decision\b",
            r"\bwe don'?t know\b",
        ),
        0.7,
        0.7,
    ),
    Rule(
        "definition",
        (
            r"\bis defined as\b",
            r"\bmeans that\b",
            r"\brefers to\b",
            r"\bstands for\b",
            r"\bwe call (?:this|it|these)\b",
            r"\bin other words\b",
        ),
        0.75,
        0.6,
    ),
    Rule(
        "architecture",
        (
            # A bare noun ("api", "table") matches nearly every sentence in a
            # technical spec. Require a structural relationship, not a mention.
            r"\b(?:service|microservice|endpoint|api|schema|database|table|queue|worker|cache|module|component)\b"
            r"[^.]{0,60}?\b(?:calls|writes to|reads from|talks to|depends on|is backed by|exposes|consumes|"
            r"publishes|subscribes to|stores|persists|owns|returns|proxies|wraps)\b",
            r"\b(?:runs on|is deployed to|is backed by|is stored in|lives in|sits behind|sits in front of)\b",
            r"\barchitecture\b",
            r"\bintegrat(?:es|ion) with\b",
        ),
        0.65,
        0.65,
    ),
    Rule(
        "person",
        (
            r"@[a-z0-9][a-z0-9._-]{2,}",
            r"\b(?:owned by|owner is|reach out to|ask)\s+(?:the\s+)?[A-Z][a-z]+",
            r"\b[A-Z][a-z]+ team\b",
        ),
        0.65,
        0.55,
    ),
    Rule(
        "system",
        (
            r"\b(?:platform|integration|third-?party|vendor|upstream|downstream) (?:system|service|provider)\b",
            r"\bruns on\b",
            r"\bpowered by\b",
        ),
        0.6,
        0.55,
    ),
)

# A sentence carrying a number, date, or version is usually a concrete fact
# worth keeping even when no rule fires.
_FACT_SIGNAL_RE = re.compile(
    r"\b\d+\s*(?:days?|hours?|minutes?|seconds?|weeks?|months?|years?|%|percent|ms|mb|gb|requests?|users?)\b"
    r"|\bv?\d+\.\d+"
    r"|\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)


class MemoryExtractor(ABC):
    name: str = "base"

    @abstractmethod
    async def extract(self, text: str, metadata: dict | None = None) -> list[ExtractedMemory]: ...


class HeuristicMemoryExtractor(MemoryExtractor):
    """Rule-based extraction. Deterministic, offline, no model provider.

    Precision over recall on purpose: a memory store full of restated prose is
    worse than a small one, because every later retrieval pays for the noise.
    """

    name = "heuristic"

    async def extract(self, text: str, metadata: dict | None = None) -> list[ExtractedMemory]:
        metadata = metadata or {}
        out: list[ExtractedMemory] = []
        seen: set[str] = set()

        for raw in _SENTENCE_SPLIT_RE.split(text or ""):
            sentence = _WHITESPACE_RE.sub(" ", raw).strip(" -*#>\t")
            if not _is_candidate(sentence):
                continue

            match = _classify(sentence)
            if match is None:
                continue
            memory_type, confidence, importance = match

            key = _dedupe_key(sentence)
            if key in seen:
                continue
            seen.add(key)

            out.append(
                ExtractedMemory(
                    type=memory_type,
                    content=sentence,
                    confidence=round(confidence, 2),
                    importance=round(importance, 2),
                    metadata={**metadata, "source_quote": sentence, "extractor": self.name},
                )
            )

        # Strongest signals first. The per-source cap is applied by the caller,
        # which is the only place that sees all of a source's documents.
        out.sort(key=lambda m: (m.importance, m.confidence), reverse=True)
        return out


def _is_candidate(sentence: str) -> bool:
    if not (MIN_SENTENCE_CHARS <= len(sentence) <= MAX_SENTENCE_CHARS):
        return False
    if _CODEISH_RE.search(sentence) or _TABLE_ROW_RE.search(sentence):
        return False
    if _FRAGMENT_START_RE.match(sentence) or _TRUNCATED_END_RE.search(sentence):
        # Begins or ends mid-clause: wreckage from a split, not a claim.
        return False
    if len(sentence.split()) < MIN_SENTENCE_WORDS:
        return False
    letters = sum(c.isalpha() for c in sentence)
    # Reject separators and other punctuation soup.
    return letters >= len(sentence) * 0.5


def _classify(sentence: str) -> tuple[str, float, float] | None:
    for rule in RULES:
        for pattern in rule.patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                confidence = rule.base_confidence
                importance = rule.base_importance
                if _FACT_SIGNAL_RE.search(sentence):
                    # Something concrete and checkable, not just a claim.
                    confidence = min(0.95, confidence + 0.05)
                    importance = min(0.95, importance + 0.05)
                return rule.type, confidence, importance

    if _FACT_SIGNAL_RE.search(sentence):
        return "fact", 0.6, 0.5
    return None


def _dedupe_key(sentence: str) -> str:
    return _WHITESPACE_RE.sub(" ", re.sub(r"[^a-z0-9 ]", "", sentence.lower())).strip()


_EXTRACTORS: dict[str, type[MemoryExtractor]] = {"heuristic": HeuristicMemoryExtractor}


def get_memory_extractor(name: str | None = None) -> MemoryExtractor:
    key = (name or get_settings().memory_extractor).lower()
    try:
        return _EXTRACTORS[key]()
    except KeyError:
        raise ValueError(
            f"Unknown memory extractor {key!r}. Available: {', '.join(sorted(_EXTRACTORS))}"
        ) from None


def register_extractor(name: str, extractor: type[MemoryExtractor]) -> None:
    """Used by later phases to add model-backed extractors."""
    _EXTRACTORS[name] = extractor
