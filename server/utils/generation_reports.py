"""File-based per-note generation-quality reports (plan refs B2/C3).

Why files and not the encrypted DB: generation telemetry is operational
metadata (verdicts, flag counts, hashes), not clinical content — it must not
bloat schema migrations, yet it must survive for nightly benchmark gates and
the /api/audit stats endpoint. A capped rolling JSONL plus per-report JSON
files under the existing data directory gives durability without a migration.

Everything here is best-effort and silent on failure: a broken telemetry file
must never affect what the clinician sees.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_INDEX_LINES = 1000


def _report_dir() -> Path:
    from server.constants import DATA_DIR

    directory = Path(DATA_DIR) / "generation_reports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def transcript_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def record_generation(
    *,
    note_id: int | None,
    template_key: str | None,
    transcript: str,
    fields: dict[str, str],
    verification: dict[str, Any] | None,
    asr_flags: list[dict[str, Any]] | None = None,
    asr_segments: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> Path | None:
    """Persist one quality report; returns the file path (None on failure)."""
    try:
        verification = verification or {}
        flag_summary: dict[str, int] = {}
        for key in ("unsupportedQuotes", "numberProblems", "negationProblems", "refinementReverts"):
            items = verification.get(key) or []
            if items:
                flag_summary[key] = len(items)
        entailment = verification.get("entailment") or {}
        report = {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "epoch_ms": int(time.time() * 1000),
            "note_id": note_id,
            "template_key": template_key,
            "model": model,
            "transcript_sha256": transcript_sha256(transcript),
            "transcript_chars": len(transcript or ""),
            "field_hashes": {
                key: hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:16]
                for key, value in (fields or {}).items()
            },
            "verification": verification,
            "asr_flag_summary": {
                "total": len(asr_flags or []),
                "low_confidence": sum(
                    1 for f in (asr_flags or []) if f.get("reason") == "low_confidence"
                ),
                "suspect": sum(1 for f in (asr_flags or []) if f.get("reason") == "suspect"),
                "artifact": sum(
                    1
                    for f in (asr_flags or [])
                    if f.get("reason")
                    in {"known_hallucination_artifact", "repetition_loop", "duplicated_line"}
                ),
            },
            "segment_count": len(asr_segments or []),
            "entailment_counts": entailment.get("counts") or {},
        }
        directory = _report_dir()
        path = directory / f"greport-{report['epoch_ms']}-{report['transcript_sha256'][:8]}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

        index = directory / "generation_reports.jsonl"
        line = json.dumps(
            {
                "epoch_ms": report["epoch_ms"],
                "note_id": note_id,
                "file": path.name,
                "flags": flag_summary,
                "asr": report["asr_flag_summary"],
                "entailment": report["entailment_counts"],
            },
            ensure_ascii=False,
        )
        try:
            existing = index.read_text(encoding="utf-8").splitlines()[-(_MAX_INDEX_LINES - 1) :]
        except OSError:
            existing = []
        existing.append(line)
        index.write_text("\n".join(existing) + "\n", encoding="utf-8")
        return path
    except Exception:  # noqa: BLE001 — telemetry must never break the note flow
        logger.debug("generation report write skipped", exc_info=True)
        return None


def _iter_index() -> list[dict[str, Any]]:
    try:
        lines = (
            (_report_dir() / "generation_reports.jsonl").read_text(encoding="utf-8").splitlines()
        )
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def latest_for_note(note_id: int) -> dict[str, Any] | None:
    """Full report dict for the most recent generation on a note, if any."""
    for entry in _iter_index():
        if entry.get("note_id") == note_id:
            try:
                return json.loads((_report_dir() / entry["file"]).read_text(encoding="utf-8"))
            except (OSError, ValueError, KeyError):
                continue
    return None


def stats(limit: int = 200) -> dict[str, Any]:
    """Aggregate verification telemetry for the audit stats endpoint (C3)."""
    entries = _iter_index()[:limit]
    total = len(entries)
    flagged = 0
    counters: dict[str, int] = {}
    for entry in entries:
        has_flag = False
        for source in ("flags", "asr"):
            for key, value in (entry.get(source) or {}).items():
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
                if value:
                    has_flag = True
                    counters[f"{source}:{key}"] = counters.get(f"{source}:{key}", 0) + value
        entailment = entry.get("entailment") or {}
        if int(entailment.get("flagged") or 0) > 0:
            has_flag = True
            counters["entailment:flagged"] = counters.get("entailment:flagged", 0) + int(
                entailment["flagged"]
            )
        if has_flag:
            flagged += 1
    return {
        "reports": total,
        "flagged": flagged,
        "clean": total - flagged,
        "counters": counters,
    }
