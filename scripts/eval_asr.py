#!/usr/bin/env python3
"""ASR quality evaluation harness (plan W2.6).

Runs batch transcription over the gold audio set in ``data/eval/`` (each
``<stem>.wav|mp3|m4a`` paired with a ``<stem>.txt`` reference transcript),
then reports:

* **WER** on raw tokens, and
* **script-normalized WER** — both sides mapped to one canonical form:
  Persian digits, Persian YK (ی/ک), casefolded, ZWNJ and punctuation
  removed. ZWNJ is semantic in Persian prose but irrelevant to scoring,
  so it is stripped symmetrically for the score only (never in output).

Optionally computes **BERTScore** (``--bert-score``) when the optional
``bert-score`` package is installed (``pip install bert-score`` — heavy,
torch-based, so it is *not* a project dependency and stays manual).

The result is compared against the committed baseline JSON
(``docs/eval/asr_baseline.json``); a regression beyond ``--tolerance``
exits non-zero. ``--update-baseline`` rewrites the baseline from the
current run. ``--compare A B`` runs two engine specs (``local``,
``speechmatics``, optionally ``engine:model-name``) side by side for
model A/B decisions.

Manual-run only (needs ASR model weights / provider keys) — it is
deliberately NOT wired into CI. The pure scoring helpers used here are
unit-tested without weights (see ``server/tests/test_eval_asr.py``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "eval"
DEFAULT_BASELINE = REPO_ROOT / "docs" / "eval" / "asr_baseline.json"

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}

# Arabic-Indic digits (U+0660..) and Latin digits map to Extended
# Persian digits (U+06F0..), the project's canonical digit script.
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹")
_LATIN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
# Arabic Yeh/Kaf -> Persian Yeh/Kaf.
_YK = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی", "ئ": "ی"})

# ZWNJ is deleted outright (it joins parts of one word); other punctuation
# becomes a token separator.
_ZWNJ = re.compile(r"\u200c")
_PUNCT = re.compile(
    r"[\u060c\u061b\u061f\u0640.,;:!?'\"()\[\]{}«»“”–—/\\|<>~`^*_=+@#$%&]+"
)
_WS = re.compile(r"\s+")


def canonicalize(text: str) -> str:
    """Canonical script form: Persian digits, Persian YK, casefolded."""
    out = text.translate(_AR_DIGITS).translate(_LATIN_DIGITS).translate(_YK)
    return out.casefold()


def score_tokens(text: str) -> list[str]:
    """Tokenize for scoring: canonical form, no ZWNJ, no punctuation."""
    cleaned = _ZWNJ.sub("", canonicalize(text))
    cleaned = _PUNCT.sub(" ", cleaned)
    return _WS.split(cleaned.strip()) if cleaned.strip() else []


def word_error_rate(ref_tokens: list[str], hyp_tokens: list[str]) -> dict[str, Any]:
    """Classic Levenshtein WER with substitution/deletion/insertion counts."""
    n, m = len(ref_tokens), len(hyp_tokens)
    if n == 0:
        return {
            "wer": 0.0 if m == 0 else 1.0,
            "substitutions": 0,
            "deletions": 0,
            "insertions": m,
            "ref_tokens": 0,
        }
    # DP with backtrace counts (O(n*m); transcripts are short).
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    ops = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
        ops[i][0] = "D"
    for j in range(m + 1):
        cost[0][j] = j
        ops[0][j] = "I"
    ops[0][0] = ""
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_tokens[i - 1] == hyp_tokens[j - 1]:
                cost[i][j] = cost[i - 1][j - 1]
                ops[i][j] = "M"
            else:
                best = min(
                    (cost[i - 1][j - 1] + 1, "S"),
                    (cost[i - 1][j] + 1, "D"),
                    (cost[i][j - 1] + 1, "I"),
                )
                cost[i][j], ops[i][j] = best
    subs = dels = ins = 0
    i, j = n, m
    while i > 0 or j > 0:
        op = ops[i][j]
        if op == "S":
            subs += 1
            i -= 1
            j -= 1
        elif op == "D":
            dels += 1
            i -= 1
        elif op == "I":
            ins += 1
            j -= 1
        else:  # match
            i -= 1
            j -= 1
    return {
        "wer": cost[n][m] / n,
        "substitutions": subs,
        "deletions": dels,
        "insertions": ins,
        "ref_tokens": n,
    }


def collect_gold_set(data_dir: Path) -> list[dict[str, Path]]:
    """Find audio files with a paired .txt reference transcript."""
    items: list[dict[str, Path]] = []
    if not data_dir.is_dir():
        return items
    for audio in sorted(data_dir.iterdir()):
        if audio.suffix.lower() not in AUDIO_EXTS:
            continue
        ref = audio.with_suffix(".txt")
        if ref.is_file():
            items.append({"audio": audio, "ref": ref})
        else:
            print(f"skip: no reference transcript for {audio.name}", file=sys.stderr)
    return items


def parse_engine_spec(spec: str) -> tuple[str, str | None]:
    """``engine[:model]`` -> (engine, model). Engine must be known."""
    engine, _, model = spec.partition(":")
    engine = engine.strip().lower()
    if engine not in {"local", "speechmatics"}:
        raise ValueError(f"unknown engine {engine!r} (use local | speechmatics)")
    return engine, model.strip() or None


def _override_engine(provider: str, model: str | None) -> None:
    """Point the in-process config at the requested engine (no DB writes)."""
    import server.transcription.audio as audio_mod

    cfg = dict(audio_mod.config_manager.get_config())
    cfg["ASR_PROVIDER"] = provider
    if model:
        cfg["ASR_MODEL"] = model
        cfg["WHISPER_MODEL"] = model
    audio_mod.config_manager.get_config = lambda: cfg  # type: ignore[method-assign]


async def transcribe_file(audio_path: Path) -> str:
    """Run the full production file path (denoise->VAD->ASR) on one clip."""
    from server.transcription.audio import transcribe_audio

    audio_bytes = audio_path.read_bytes()
    result = await transcribe_audio(audio_bytes)
    return str(result.get("text") or "").strip()


def evaluate_set(
    items: list[dict[str, Path]],
    provider: str,
    model: str | None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Transcribe every gold clip and score it (raw + normalized WER)."""
    import asyncio

    _override_engine(provider, model)

    files: list[dict[str, Any]] = []
    total_raw = {"errors": 0, "ref_tokens": 0}
    total_norm = {"errors": 0, "ref_tokens": 0}
    wer_list: list[float] = []
    norm_wer_list: list[float] = []
    refs: list[str] = []
    hyps: list[str] = []

    for item in items:
        hypothesis = asyncio.run(transcribe_file(item["audio"]))
        reference = item["ref"].read_text(encoding="utf-8").strip()
        raw = word_error_rate(reference.split(), hypothesis.split())
        norm = word_error_rate(score_tokens(reference), score_tokens(hypothesis))
        errors_raw = raw["substitutions"] + raw["deletions"] + raw["insertions"]
        errors_norm = norm["substitutions"] + norm["deletions"] + norm["insertions"]
        total_raw["errors"] += errors_raw
        total_raw["ref_tokens"] += raw["ref_tokens"]
        total_norm["errors"] += errors_norm
        total_norm["ref_tokens"] += norm["ref_tokens"]
        wer_list.append(raw["wer"])
        norm_wer_list.append(norm["wer"])
        refs.append(reference)
        hyps.append(hypothesis)
        entry = {
            "file": item["audio"].name,
            "wer": round(raw["wer"], 4),
            "normalized_wer": round(norm["wer"], 4),
        }
        files.append(entry)
        if verbose:
            print(
                f"  {item['audio'].name}: WER {raw['wer']:.3f} (norm {norm['wer']:.3f})"
            )

    micro = (
        total_raw["errors"] / total_raw["ref_tokens"]
        if total_raw["ref_tokens"]
        else 0.0
    )
    norm_micro = (
        total_norm["errors"] / total_norm["ref_tokens"]
        if total_norm["ref_tokens"]
        else 0.0
    )
    return {
        "engine": provider,
        "model": model,
        "files": files,
        "wer_micro": round(micro, 4),
        "wer_macro": round(sum(wer_list) / len(wer_list), 4) if wer_list else 0.0,
        "normalized_wer_micro": round(norm_micro, 4),
        "normalized_wer_macro": (
            round(sum(norm_wer_list) / len(norm_wer_list), 4) if norm_wer_list else 0.0
        ),
        "_refs": refs,
        "_hyps": hyps,
    }


def compute_bert_score(refs: list[str], hyps: list[str]) -> float:
    """Mean BERTScore F1 over the set; needs the optional bert-score pkg."""
    try:
        from bert_score import score as bert_score_fn  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - manual-run path
        raise SystemExit(
            "BERTScore unavailable: install the optional package first "
            "(pip install bert-score). It is intentionally not a project "
            "dependency because it pulls in torch."
        ) from exc
    _p, _r, f1 = bert_score_fn(hyps, refs, lang="fa", verbose=False)
    return round(float(f1.mean()), 4)


def check_regression(
    result: dict[str, Any],
    baseline: dict[str, Any],
    tolerance: float,
) -> list[str]:
    """Return human-readable regression findings (empty list = no regression)."""
    findings: list[str] = []
    pairs = [
        ("wer_micro", "WER (micro)", +1),  # higher is worse
        ("normalized_wer_micro", "normalized WER (micro)", +1),
    ]
    for key, label, direction in pairs:
        base = baseline.get(key)
        cur = result.get(key)
        if base is None or cur is None:
            continue
        if direction * (cur - base) > tolerance:
            findings.append(
                f"{label} regressed: {base:.4f} -> {cur:.4f} (tol {tolerance})"
            )
    base_f1 = baseline.get("bert_score_f1")
    cur_f1 = result.get("bert_score_f1")
    if base_f1 is not None and cur_f1 is not None and (base_f1 - cur_f1) > tolerance:
        findings.append(f"BERTScore F1 regressed: {base_f1:.4f} -> {cur_f1:.4f}")
    return findings


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in result.items() if not k.startswith("_")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--engine",
        default="local",
        help="engine spec: local | speechmatics, optionally engine:model",
    )
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--bert-score", action="store_true")
    parser.add_argument("--tolerance", type=float, default=0.005)
    parser.add_argument("--limit", type=int, default=0, help="only score first N clips")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("A", "B"),
        help="run two engine specs side by side instead of baseline comparison",
    )
    args = parser.parse_args(argv)

    items = collect_gold_set(args.data_dir)
    if args.limit > 0:
        items = items[: args.limit]
    if not items:
        print(
            f"no gold clips with references in {args.data_dir} — add <stem>.wav + "
            "<stem>.txt pairs (see data/eval/README.md)",
            file=sys.stderr,
        )
        return 2

    if args.compare:
        spec_a, spec_b = (parse_engine_spec(s) for s in args.compare)
        print(f"=== engine A: {spec_a[0]} {spec_a[1] or ''} ===")
        result_a = evaluate_set(items, spec_a[0], spec_a[1], verbose=args.verbose)
        print(f"=== engine B: {spec_b[0]} {spec_b[1] or ''} ===")
        result_b = evaluate_set(items, spec_b[0], spec_b[1], verbose=args.verbose)
        print(
            f"\n{'file':40s} {'A WER':>8s} {'B WER':>8s} {'A norm':>8s} {'B norm':>8s}"
        )
        for fa, fb in zip(result_a["files"], result_b["files"]):
            print(
                f"{fa['file']:40s} {fa['wer']:8.4f} {fb['wer']:8.4f} "
                f"{fa['normalized_wer']:8.4f} {fb['normalized_wer']:8.4f}"
            )
        print(
            f"\nmacro WER  A={result_a['wer_macro']:.4f} B={result_b['wer_macro']:.4f}\n"
            f"micro WER  A={result_a['wer_micro']:.4f} B={result_b['wer_micro']:.4f}\n"
            f"norm micro A={result_a['normalized_wer_micro']:.4f} "
            f"B={result_b['normalized_wer_micro']:.4f}"
        )
        return 0

    provider, model = parse_engine_spec(args.engine)
    print(f"evaluating {len(items)} clips with {provider} {model or '(default model)'}")
    result = evaluate_set(items, provider, model, verbose=args.verbose)
    if args.bert_score:
        result["bert_score_f1"] = compute_bert_score(result["_refs"], result["_hyps"])

    print(
        f"WER micro={result['wer_micro']:.4f} macro={result['wer_macro']:.4f} | "
        f"normalized micro={result['normalized_wer_micro']:.4f} "
        f"macro={result['normalized_wer_macro']:.4f}"
    )
    if "bert_score_f1" in result:
        print(f"BERTScore F1 mean={result['bert_score_f1']:.4f}")

    if args.update_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        payload = _public_result(result)
        payload["data_dir"] = str(args.data_dir)
        args.baseline.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"baseline written: {args.baseline}")
        return 0

    if args.baseline.is_file():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        if baseline.get("wer_micro") is None:
            print("baseline is an unfilled template — run with --update-baseline first")
            return 0
        findings = check_regression(result, baseline, args.tolerance)
        if findings:
            print("REGRESSION vs baseline:", file=sys.stderr)
            for line in findings:
                print(f"  - {line}", file=sys.stderr)
            return 1
        print("no regression vs baseline")
        return 0

    print(f"no baseline at {args.baseline} — run with --update-baseline to create it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
