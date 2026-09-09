#!/usr/bin/env python3
"""One-off provenance backfill for the medical term lists (W2.4).

Adds the optional ``src`` field to every entry in ``server/data/terms``:

* ``generated.json`` / ``expanded.json``  -> ``"src": "generated"``
  (machine-generated combinatorial lists),
* every other term file                  -> ``"src": "curated"``.

The script is idempotent (existing ``src`` values are kept) and preserves
each file's exact formatting: ``generated.json`` keeps its compact
one-entry-per-line style without a trailing newline, all other files keep
their 2-space-indent style. After rewriting, the real validator runs on the
merged set and the script fails loudly if anything became invalid.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMS_DIR = ROOT / "server" / "data" / "terms"

sys.path.insert(0, str(ROOT / "server" / "data"))
from validate_terms import validate_all

GENERATED_FILES = {"generated.json", "expanded.json"}


def _entry_with_src(entry: dict, src: str) -> dict:
    if "src" in entry:
        return entry  # idempotent: never overwrite an existing provenance
    rebuilt = {}
    for key, value in entry.items():
        rebuilt[key] = value
        if key == "cat":  # provenance sits right after the identity fields
            rebuilt["src"] = src
    if "src" not in rebuilt:
        rebuilt["src"] = src
    return rebuilt


def _dump(data: list[dict], original: str) -> str:
    """Serialize in the file's original style (detected from its first lines)."""
    compact = original.lstrip().startswith("[{")
    if compact:
        return "[" + ",\n".join(json.dumps(e, ensure_ascii=False) for e in data) + "]"
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    changed = 0
    for path in sorted(TERMS_DIR.glob("*.json")):
        original = path.read_text(encoding="utf-8")
        data = json.loads(original)
        src = "generated" if path.name in GENERATED_FILES else "curated"
        updated = [_entry_with_src(e, src) for e in data]
        if updated == data:
            print(f"skip    {path.name} (already backfilled)")
            continue
        path.write_text(_dump(updated, original), encoding="utf-8", newline="\n")
        changed += 1
        print(f"backfill {path.name}: {len(updated)} entries -> src={src!r}")

    entries = validate_all()
    print(f"validator green: {len(entries)} entries across {changed} rewritten files")


if __name__ == "__main__":
    main()
