"""Gold/planted-error scorer for the note-faithfulness verification.

Run from the repo root (same as the nightly precision gate)::

    python3 -m server.bench.score_notes --verbose

Acceptance contract:

* every pair in ``gold/note_pairs.jsonl`` must produce ZERO findings —
  a faithful note must never be flagged;
* every row in ``gold/planted_errors.jsonl`` must produce a finding whose
  ``kind`` equals ``expect_kind`` — the detectors must catch the specific
  planted error class;
* when ``--baseline path/to/baseline.json`` is given, gold findings must not
  increase and the planted catch rate must not decrease.

Stdlib-only so the bare nightly runner can execute it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from server.bench.guards import verify_note

_GOLD_DEFAULT = Path(__file__).resolve().parent.parent / "tests" / "gold" / "note_pairs.jsonl"
_PLANTED_DEFAULT = (
    Path(__file__).resolve().parent.parent / "tests" / "gold" / "planted_errors.jsonl"
)


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not row.get("id") or not row.get("source") or not row.get("note"):
                raise SystemExit(f"{path}:{line_no}: each row needs 'id', 'source', 'note'")
            rows.append(row)
    return rows


def score_gold(rows: list[dict], *, verbose: bool = False) -> tuple[int, list[str]]:
    """Returns (number of flagged pairs, failure descriptions)."""
    failures: list[str] = []
    flagged = 0
    for row in rows:
        result = verify_note(row["source"], row["note"])
        if result.findings:
            flagged += 1
            detail = "; ".join(f"{f.kind}: {f.detail}" for f in result.findings)
            failures.append(f"{row['id']}: {detail}")
            if verbose:
                print(f"FAIL(gold)  {row['id']}: {detail}")
        elif verbose:
            print(f"PASS  {row['id']}")
    return flagged, failures


def score_planted(rows: list[dict], *, verbose: bool = False) -> tuple[int, list[str]]:
    """Returns (number of caught planted errors, failure descriptions)."""
    failures: list[str] = []
    caught = 0
    for row in rows:
        expect = row.get("expect_kind", "")
        result = verify_note(row["source"], row["note"])
        kinds = {f.kind for f in result.findings}
        if expect in kinds:
            caught += 1
            if verbose:
                print(f"PASS  {row['id']}  [{expect}]")
        else:
            found = ", ".join(sorted(kinds)) or "no findings"
            failures.append(f"{row['id']}: expected [{expect}], found [{found}]")
            if verbose:
                print(f"FAIL(plant) {row['id']}: expected [{expect}], found [{found}]")
    return caught, failures


def _load_baseline(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def compare_baseline(current: dict, baseline: dict, *, verbose: bool = False) -> list[str]:
    regressions: list[str] = []
    if current["gold_findings"] > baseline.get("gold_findings", 0):
        regressions.append(
            "gold findings increased: "
            f"{current['gold_findings']} > baseline {baseline.get('gold_findings')}"
        )
    if current["catch_rate"] < baseline.get("catch_rate", 0.0):
        regressions.append(
            "planted catch rate decreased: "
            f"{current['catch_rate']:.2%} < baseline {baseline.get('catch_rate', 0.0):.2%}"
        )
    if verbose and not regressions:
        print("baseline: no regression")
    return regressions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="server.bench.score_notes")
    parser.add_argument("--gold", type=Path, default=_GOLD_DEFAULT)
    parser.add_argument("--planted", type=Path, default=_PLANTED_DEFAULT)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="baseline.json produced by an earlier run; fail on regression",
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable summary")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    gold_rows = _load_jsonl(args.gold)
    plant_rows = _load_jsonl(args.planted)
    gold_findings, gold_failures = score_gold(gold_rows, verbose=args.verbose)
    caught, plant_failures = score_planted(plant_rows, verbose=args.verbose)
    catch_rate = caught / len(plant_rows) if plant_rows else 1.0

    summary = {
        "gold_pairs": len(gold_rows),
        "gold_findings": gold_findings,
        "planted_errors": len(plant_rows),
        "planted_caught": caught,
        "catch_rate": catch_rate,
    }

    regressions: list[str] = []
    if args.baseline:
        regressions = compare_baseline(summary, _load_baseline(args.baseline), verbose=args.verbose)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    if gold_failures or plant_failures or regressions:
        for message in gold_failures + plant_failures + regressions:
            print(f"score_notes: {message}", file=sys.stderr)
        return 1
    if args.verbose:
        print(
            f"scorer: {len(gold_rows)} gold pairs clean, "
            f"{caught}/{len(plant_rows)} planted errors caught"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
