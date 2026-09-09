"""Stdlib verification guards for planted precision fixtures.

These catch the failure modes the nightly comment lists: fabricated clinical
claims, numeric drift, and negation flips. They are intentionally conservative
and have no third-party imports so the gate stays runnable on a bare runner.
"""

from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_TOKEN_RE = re.compile(r"[A-Za-z0-9؀-ۿ]{2,}")
_SENTENCE_RE = re.compile(r"[.\n؛]+")

_NEGATION_PAIRS: tuple[tuple[str, str], ...] = (
    ("ندارد", "دارد"),
    ("نیست", "است"),
    ("نمی‌کند", "می‌کند"),
    ("نمي‌کند", "مي‌کند"),
)


def extract_numbers(text: str) -> set[str]:
    return {match.replace(",", ".") for match in _NUMBER_RE.findall(text or "")}


def detect_number_drift(source: str, generated: str) -> list[str]:
    """Return numbers that appear in ``generated`` but not in ``source``."""
    return sorted(extract_numbers(generated) - extract_numbers(source))


def detect_negation_flip(source: str, generated: str) -> list[str]:
    """Return polarity pairs that flipped from negated in source to affirmed."""
    flips: list[str] = []
    for negative, positive in _NEGATION_PAIRS:
        if negative in source and positive in generated and negative not in generated:
            flips.append(f"{negative}->{positive}")
    return flips


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text or "")}


def detect_fabrication(source: str, generated: str) -> list[str]:
    """Return generated sentences whose content is not grounded in ``source``."""
    source_tokens = _tokens(source)
    issues: list[str] = []
    for sentence in _SENTENCE_RE.split(generated or ""):
        sentence = sentence.strip()
        tokens = _tokens(sentence)
        if len(tokens) < 2:
            continue
        overlap = tokens & source_tokens
        if len(overlap) / len(tokens) < 0.25:
            issues.append(sentence)
    return issues
