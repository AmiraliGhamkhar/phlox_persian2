#!/usr/bin/env python3
"""ASR model benchmark — WER / CER / Missed-Entity-Rate against references.

Part of the precision program (docs/phlox-accuracy-hallucination-plan.md,
plan ref A7). This script does NOT train or run models: each candidate ASR
system produces a hypothesis text file, and this tool scores them against
the same references so the comparison is apples-to-apples. The matrix
commands that produce the hypothesis files live in docs/asr-benchmark.md.

Expected layout (one .txt per reference):

    refs/          # gold transcripts (what was actually said)
      fa-reflux-001.txt
      en-gerd-004.txt
    hyp_whisper-large-v3/
      fa-reflux-001.txt
      en-gerd-004.txt
    hyp_faster-whisper-turbo/
      ...

Usage:
    python -m server.bench.asr_scorer --refs refs --hyp hyp_a hyp_b
    python -m server.bench.asr_scorer --from-fixtures server/bench/fixtures/precision_fa_en.jsonl --hyp DIR
    python -m server.bench.asr_scorer --ref r.txt --hyp h.txt --json report.json

Metrics:
    WER  word error rate = edit_distance(ref, hyp) / len(ref)
    CER  character error rate on space-free normalized characters
    MER  missed-entity rate: fraction of reference numeric facts (values +
         units) and salient Latin terms missing or altered in the hypothesis
         — the clinical-error proxy used by the AWS/AssemblyAI literature.

Normalization reuses Phlox's own match-normalizer (Persian/Arabic digit and
script folding, ZWNJ, punctuation), so scores reflect what the note pipeline
actually sees. If run outside the repo, a built-in fallback normalizer with
the same rules applies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

try:  # the app's own normalizer — same rules the note pipeline applies
    from server.transcription.verification import extract_numbers, normalize_for_match
except Exception:  # noqa: BLE001 — standalone fallback when run outside the app
    _FOLD = str.maketrans(
        {
            **{c: str(i % 10) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩")},
            "ي": "ی",
            "ك": "ک",
            "ة": "ه",
            "ى": "ی",
            "،": " ",
            "؛": " ",
            "؟": " ",
            "٫": ".",
            "٬": ",",
        }
    )

    def normalize_for_match(text: str) -> str:
        if not text:
            return ""
        t = unicodedata.normalize("NFC", text)
        t = "".join(c for c in unicodedata.normalize("NFD", t) if not unicodedata.combining(c))
        t = t.translate(_FOLD).replace("\u200c", " ")
        t = t.lower()
        t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)
        t = re.sub(r"(?<!\d)\.(?!\d)", " ", t)
        t = re.sub(r"[^0-9a-z.\u0600-\u06ff ]+", " ", t)
        return re.sub(r" +", " ", t).strip()

    def extract_numbers(text: str) -> list[dict[str, Any]]:
        norm = normalize_for_match(text)
        return [
            {"value": m.group(0).replace(",", ""), "unit": None, "context": ""}
            for m in re.finditer(r"\d+(?:\.\d+)?", norm)
        ]


try:  # fast path when the dependency is installed
    from rapidfuzz.distance import Levenshtein as _Levenshtein

    def _edit_distance(a, b) -> int:
        return _Levenshtein.distance(a, b)
except ImportError:  # plain-laptop fallback (mirrors verification.py's deps)

    def _edit_distance(a, b) -> int:
        if len(a) < len(b):
            a, b = b, a
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            prev = cur
        return prev[len(b)]


# Latin clinical-ish terms worth tracking for MER: drug-like words, doses with
# units, and identifiers. Heuristic on purpose — it must not depend on an NER
# model to run on a plain laptop.
_LATIN_TERM_RE = re.compile(r"[a-z][a-z0-9-]{4,}")


def wer(ref: str, hyp: str) -> float:
    a, b = ref.split(), hyp.split()
    if not a:
        return 0.0 if not b else 1.0
    return _edit_distance(a, b) / len(a)


def cer(ref: str, hyp: str) -> float:
    a = ref.replace(" ", "")
    b = hyp.replace(" ", "")
    if not a:
        return 0.0 if not b else 1.0
    return _edit_distance(a, b) / len(a)


def entity_set(text: str) -> set[str]:
    entities = {f"num:{n['value']}" for n in extract_numbers(text)}
    entities |= {f"tok:{t}" for t in _LATIN_TERM_RE.findall(text)}
    return entities


def mer(ref: str, hyp: str) -> tuple[float, dict]:
    ref_entities, hyp_entities = entity_set(ref), entity_set(hyp)
    missed = sorted(ref_entities - hyp_entities)
    hallucinated = sorted(hyp_entities - ref_entities)
    rate = len(missed) / len(ref_entities) if ref_entities else 0.0
    return rate, {"missed": missed, "hallucinated_entities": hallucinated}


def score_pair(ref_text: str, hyp_text: str) -> dict:
    r = normalize_for_match(ref_text)
    h = normalize_for_match(hyp_text)
    miss_rate, detail = mer(r, h)
    return {
        "wer": round(wer(r, h), 4),
        "cer": round(cer(r, h), 4),
        "mer": round(miss_rate, 4),
        **detail,
    }


def aggregate(scores: list[dict]) -> dict:
    if not scores:
        return {}
    keys = ("wer", "cer", "mer")
    out = {key: round(sum(s[key] for s in scores) / len(scores), 4) for key in keys}
    out["files"] = len(scores)
    out["missed_total"] = sum(len(s["missed"]) for s in scores)
    return out


def load_fixtures_refs(path: Path) -> dict[str, str]:
    refs: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw = json.loads(line)
        refs[raw["id"]] = raw["transcript"]
    return refs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refs", type=Path, help="directory of reference .txt files")
    parser.add_argument(
        "--from-fixtures",
        type=Path,
        help="benchmark JSONL whose 'transcript' fields are references",
    )
    parser.add_argument("--ref", type=Path, help="single reference file")
    parser.add_argument(
        "--hyp",
        type=Path,
        nargs="+",
        required=True,
        help="hypothesis dir(s) or file(s)",
    )
    parser.add_argument("--json", type=Path, help="write full report JSON here")
    parser.add_argument(
        "--max-wer",
        type=float,
        default=None,
        help="exit non-zero if aggregate WER exceeds this (gate mode)",
    )
    parser.add_argument(
        "--max-mer",
        type=float,
        default=None,
        help="exit non-zero if aggregate MER exceeds this (gate mode)",
    )
    args = parser.parse_args(argv)

    if args.from_fixtures:
        refs = load_fixtures_refs(args.from_fixtures)
    elif args.refs:
        refs = {p.stem: p.read_text(encoding="utf-8") for p in sorted(args.refs.glob("*.txt"))}
    elif args.ref:
        refs = {args.ref.stem: args.ref.read_text(encoding="utf-8")}
    else:
        parser.error("provide --refs DIR or --from-fixtures FILE or --ref FILE")

    if not refs:
        print("no references found", file=sys.stderr)
        return 2

    report: dict[str, dict] = {}
    any_error = False
    for hyp_source in args.hyp:
        label = hyp_source.stem if hyp_source.is_dir() else hyp_source.name
        scores: dict[str, dict] = {}
        for ref_id, ref_text in sorted(refs.items()):
            hyp_path = (hyp_source / f"{ref_id}.txt") if hyp_source.is_dir() else hyp_source
            if not hyp_path.exists():
                print(f"[{label}] missing hypothesis for {ref_id}", file=sys.stderr)
                any_error = True
                continue
            result = score_pair(ref_text, hyp_path.read_text(encoding="utf-8"))
            scores[ref_id] = result
            print(
                f"[{label}] {ref_id}: WER={result['wer']:.3f} CER={result['cer']:.3f} "
                f"MER={result['mer']:.3f}"
                + (f" missed={', '.join(result['missed'][:6])}" if result["missed"] else "")
            )
        summary = aggregate(list(scores.values()))
        if summary:
            print(
                f"[{label}] AGGREGATE: WER={summary['wer']:.3f} CER={summary['cer']:.3f} "
                f"MER={summary['mer']:.3f} over {summary['files']} files"
            )
        report[label] = {"per_file": scores, "aggregate": summary}
        if args.max_wer is not None and summary and summary["wer"] > args.max_wer:
            any_error = True
        if args.max_mer is not None and summary and summary["mer"] > args.max_mer:
            any_error = True

    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if any_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
