"""Stdlib-only offline precision gate.

Invoked by ``.github/workflows/nightly.yml`` as::

    python3 -m server.bench.run_bench --mode offline --verbose

No LLM, database, or third-party imports: a regression in ASR hygiene,
Persian normalisation, or the verification guards must fail this process
even when Docker builds succeed.

Hygiene and language helpers are loaded from source files so
``server.transcription`` package imports (httpx, etc.) are not required.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from server.bench.guards import detect_fabrication, detect_negation_flip, detect_number_drift

_SERVER_DIR = Path(__file__).resolve().parent.parent


def _load_stdlib_module(name: str, relative: str):
    path = _SERVER_DIR / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses (and PEP 563 annotations) look the module up in sys.modules
    # while the class body is executing.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run_offline(*, verbose: bool) -> int:
    hygiene = _load_stdlib_module("phlox_hygiene", "transcription/hygiene.py")
    language = _load_stdlib_module("phlox_language", "transcription/language.py")
    detect_artifacts = hygiene.detect_artifacts
    normalize_persian_text = language.normalize_persian_text

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if verbose:
            status = "PASS" if ok else "FAIL"
            extra = f"  {detail}" if detail else ""
            print(f"{status}  {name}{extra}")
        if not ok:
            failures.append(name)

    for text in (
        "Thanks for watching and don't forget to subscribe!",
        "با تشکر از توجه شما",
        "زیرنویس توسط کلیک‌تکس",
        "الان الان الان الان الان we proceed",
    ):
        reasons = detect_artifacts(text)
        check(f"artifact:{text[:48]}", bool(reasons), ",".join(reasons) or "no flag")

    clean = "بیمار مرد ۵۲ ساله با درد قفسه سینه از دیروز"
    check("clean_clinical", detect_artifacts(clean) == [], str(detect_artifacts(clean)))

    mixed = "بيمار كبد چرب HbA1c 7.2٪"
    normalised = normalize_persian_text(mixed)
    check(
        "number_preserved_hba1c",
        "HbA1c" in normalised and "7.2" in normalised,
        normalised,
    )

    source = "بیمار مرد ۵۲ ساله با درد قفسه سینه از دیروز. HbA1c 7.2. درد شکم ندارد."
    faithful = "شکایت اصلی: درد قفسه سینه از دیروز. HbA1c 7.2. درد شکم ندارد."
    check("faithful_no_number_drift", detect_number_drift(source, faithful) == [])
    check("faithful_no_negation_flip", detect_negation_flip(source, faithful) == [])
    check("faithful_no_fabrication", detect_fabrication(source, faithful) == [])

    drifted = detect_number_drift(source, "شکایت اصلی: درد قفسه سینه. HbA1c 8.1.")
    check("number_drift_caught", "8.1" in drifted, str(drifted))

    flipped = detect_negation_flip(source, "درد شکم دارد")
    check("negation_flip_caught", bool(flipped), str(flipped))

    fabricated = detect_fabrication(source, "سابقه سکته مغزی و دیالیز سه بار در هفته")
    check("fabrication_caught", bool(fabricated), str(fabricated))

    if failures:
        print(f"{len(failures)} fixture(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    if verbose:
        print("offline precision gate: all fixtures passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="server.bench.run_bench")
    parser.add_argument("--mode", choices=("offline",), default="offline")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    return _run_offline(verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
