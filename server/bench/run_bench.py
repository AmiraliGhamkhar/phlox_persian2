"""Precision benchmark runner (plan refs C1/C2).

offline mode (default): zero-dependency gate for CI. Loads the two guard
modules straight from source (``server/transcription/verification.py`` and
``server/transcription/hygiene.py`` are stdlib-only, so neither the database
nor any model stack is needed), replays them over the fixtures and exits
non-zero unless

* every planted failure is caught by its mapped detector, and
* every gold bullet passes all guards (a fixture that no longer describes
  what the code accepts is a broken fixture).

live mode: runs the real extraction/refinement pipeline
(``server.transcription.text.process_transcription``) over the same fixtures
with the configured LLM and reports per-run metrics (claim-support,
fabrication flags, number/negation problems, entailment verdicts). Needs the
full server environment; it reports, it does not gate — model behavior must
not break the nightly build, only measure it.

Usage:
    python -m server.bench.run_bench --mode offline
    python -m server.bench.run_bench --mode live [--json out.json]
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from .dataset import Fixture, Mutation, load_fixtures

ROOT = Path(__file__).resolve().parents[2]

QUOTE_THRESHOLD = 0.85


def _load_stdlib_module(name: str, relpath: str) -> Any:
    """Load a stdlib-only server module without importing the app stack."""
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {relpath}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _check_mutation(V: Any, H: Any, fixture: Fixture, m: Mutation) -> bool:
    transcript = fixture.transcript
    if m.detector == "quote":
        _, report = V.verify_draft({m.field_key: [m.bullet]}, transcript, mode="flag")
        return bool(report.unsupported)
    if m.detector == "number":
        report = V.verify_final_fields(
            {m.field_key: V.join_bullets([m.bullet])},
            transcript,
            V.VerificationReport(mode="flag"),
        )
        return any(str(p["value"]) == str(m.detail) for p in report.number_problems)
    if m.detector == "negation":
        return bool(V.negation_conflicts([m.bullet], transcript))
    if m.detector == "artifact":
        reasons = H.detect_artifacts(m.bullet)
        return (m.detail in reasons) if m.detail else bool(reasons)
    return False


def _gold_is_clean(V: Any, fixture: Fixture) -> list[str]:
    problems: list[str] = []
    for key, bullets in fixture.gold_fields.items():
        _, report = V.verify_draft({key: bullets}, fixture.transcript, mode="flag")
        if report.unsupported:
            problems.append(
                f"{key}: unsupported gold bullet {[p['point'] for p in report.unsupported]}"
            )
        final = V.verify_final_fields(
            {key: V.join_bullets(bullets)},
            fixture.transcript,
            V.VerificationReport(mode="flag"),
        )
        if final.number_problems:
            problems.append(f"{key}: gold number flagged {final.number_problems}")
        if final.negation_problems:
            problems.append(f"{key}: gold negation flagged {final.negation_problems}")
    return problems


def run_offline(verbose: bool = False) -> dict[str, Any]:
    V = _load_stdlib_module("phlox_bench_verification", "server/transcription/verification.py")
    H = _load_stdlib_module("phlox_bench_hygiene", "server/transcription/hygiene.py")

    fixtures = load_fixtures()
    results: list[dict[str, Any]] = []
    missed: list[str] = []
    gold_problems: list[str] = []
    total_plants = 0

    for fixture in fixtures:
        gold = _gold_is_clean(V, fixture)
        gold_problems.extend(f"{fixture.id}: {p}" for p in gold)
        caught: list[str] = []
        for mutation in fixture.mutations:
            total_plants += 1
            if _check_mutation(V, H, fixture, mutation):
                caught.append(f"{mutation.kind}({mutation.detector})")
            else:
                missed.append(f"{fixture.id}:{mutation.kind}({mutation.detector})")
        results.append({"id": fixture.id, "caught": caught, "gold_ok": not gold})
        if verbose:
            status = "OK " if not gold and len(caught) == len(fixture.mutations) else "FAIL"
            print(f"[{status}] {fixture.id}: caught {len(caught)}/{len(fixture.mutations)}")

    return {
        "mode": "offline",
        "fixtures": len(fixtures),
        "plants": total_plants,
        "caught": total_plants - len(missed),
        "missed": missed,
        "gold_problems": gold_problems,
        "results": results,
    }


async def run_live() -> dict[str, Any]:
    """Run the full note pipeline over fixtures and report metrics."""
    from server.schemas.templates import TemplateField
    from server.transcription.text import process_transcription

    V = _load_stdlib_module("phlox_bench_verification_live", "server/transcription/verification.py")
    fixtures = load_fixtures()
    per_note: list[dict[str, Any]] = []
    for fixture in fixtures:
        fields = [
            TemplateField(
                field_key=key,
                field_name=key.upper(),
                field_type="list",
                system_prompt=f"Extract {key} from the transcript.",
                style_example="",
            )
            for key in fixture.gold_fields
        ]
        outcome = await process_transcription(
            transcript_text=fixture.transcript,
            template_fields=fields,
            patient_context={"name": None, "dob": None, "gender": None},
            is_ambient=True,
        )
        verification = outcome.get("verification") or {}
        generated_bullets = sum(
            len([line for line in (content or "").splitlines() if line.strip()])
            for content in (outcome.get("fields") or {}).values()
        )
        unsupported = len(verification.get("unsupportedQuotes") or [])
        numbers = len(verification.get("numberProblems") or [])
        negations = len(verification.get("negationProblems") or [])
        # Omission metric: fraction of gold facts the pipeline kept (measured
        # as the same trigram-support score, this time gold-vs-note).
        recovered = 0
        total_gold = 0
        for key, bullets in fixture.gold_fields.items():
            produced = V.normalize_for_match((outcome.get("fields") or {}).get(key, ""))
            trigrams = V._build_trigrams(produced)
            for bullet in bullets:
                total_gold += 1
                if V.quote_support(bullet, produced, trigrams) >= QUOTE_THRESHOLD:
                    recovered += 1

        per_note.append(
            {
                "id": fixture.id,
                "gold_recall": round(recovered / total_gold, 3) if total_gold else None,
                "generated_bullets": generated_bullets,
                "unsupported_quotes": unsupported,
                "number_problems": numbers,
                "negation_problems": negations,
                "entailment": verification.get("entailment") or {},
            }
        )
    bullets = sum(n["generated_bullets"] for n in per_note) or 0
    flagged = sum(
        n["unsupported_quotes"] + n["number_problems"] + n["negation_problems"] for n in per_note
    )
    return {
        "mode": "live",
        "notes": len(per_note),
        "metrics": {
            "claim_support_rate": round(1 - (flagged / bullets), 3) if bullets else None,
            "total_bullets": bullets,
            "flagged_bullets": flagged,
            "per_note": per_note,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="server.bench.run_bench")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--json", dest="json_out", default=None, help="write summary JSON here")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if args.mode == "offline":
        summary = run_offline(verbose=args.verbose)
        ok = not summary["missed"] and not summary["gold_problems"]
        print(
            f"offline gate: caught {summary['caught']}/{summary['plants']} planted failures "
            f"across {summary['fixtures']} fixtures; gold-problems={len(summary['gold_problems'])}"
        )
        for item in summary["missed"]:
            print(f"  MISSED: {item}")
        for item in summary["gold_problems"]:
            print(f"  GOLD: {item}")
    else:
        try:
            summary = asyncio.run(run_live())
        except Exception as error:  # noqa: BLE001
            print(f"live mode needs a configured server environment: {error}", file=sys.stderr)
            return 2
        metrics = summary["metrics"]
        print(
            f"live: {metrics['total_bullets']} bullets, {metrics['flagged_bullets']} flagged, "
            f"support={metrics['claim_support_rate']}"
        )
        ok = True  # live mode reports; the deterministic gate is what blocks

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
