"""Fixture dataset for the precision benchmark (plan ref C1).

Each fixture is a synthetic encounter: a transcript, the "gold" note bullets
that must pass every guard, and planted failure modes that must each be
caught by their corresponding detector. Persian and English cases, numbers,
units and negations included — mirroring the failure classes measured in the
clinical-AI literature cited in the plan doc.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "precision_fa_en.jsonl"


@dataclass
class Mutation:
    """One planted failure in field content; detector names what must fire."""

    kind: str  # fabrication | number_drift | negation_flip | artifact
    field_key: str
    bullet: str
    detail: str = ""  # e.g. the drifted number that must be reported
    detector: str = ""  # quote | number | negation | artifact

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Mutation:
        return cls(
            kind=raw["kind"],
            field_key=raw["field"],
            bullet=raw["bullet"],
            detail=str(raw.get("detail", "")),
            detector=raw.get("detector", ""),
        )


@dataclass
class Fixture:
    id: str
    lang: str
    transcript: str
    gold_fields: dict[str, list[str]] = field(default_factory=dict)
    mutations: list[Mutation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Fixture:
        return cls(
            id=raw["id"],
            lang=raw["lang"],
            transcript=raw["transcript"],
            gold_fields=dict(raw.get("gold_fields") or {}),
            mutations=[Mutation.from_dict(m) for m in raw.get("mutations") or []],
        )


def load_fixtures(path: Path | None = None) -> list[Fixture]:
    target = path or FIXTURES_PATH
    fixtures: list[Fixture] = []
    for line_no, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            fixtures.append(Fixture.from_dict(json.loads(line)))
        except (ValueError, KeyError) as exc:
            raise ValueError(f"{target}:{line_no}: malformed fixture: {exc}") from exc
    if not fixtures:
        raise ValueError(f"no fixtures loaded from {target}")
    return fixtures
