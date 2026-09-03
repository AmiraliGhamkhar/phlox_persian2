#!/usr/bin/env python3
"""Compat shim: the ASR scorer lives in the server package (tested in CI).

See server/bench/asr_scorer.py and docs/asr-benchmark.md for usage; both
``python scripts/bench_asr_models.py ...`` and ``python -m
server.bench.asr_scorer ...`` behave identically.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.bench.asr_scorer import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
