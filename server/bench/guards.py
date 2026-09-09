"""Stdlib verification guards (thin re-export — kept for the nightly gate).

The production implementation lives in :mod:`server.nlp_tools.verification`
so the live report path and the offline precision gate share one source of
truth. This module must stay importable with no third-party dependencies:
``server.bench.run_bench`` loads it on a bare runner.
"""

from server.nlp_tools.verification import (
    detect_fabrication,
    detect_negation_flip,
    detect_number_drift,
    detect_ungrounded_terms,
    detect_unit_mismatch,
    extract_numbers,
    verify_note,
)

__all__ = [
    "detect_fabrication",
    "detect_negation_flip",
    "detect_number_drift",
    "detect_ungrounded_terms",
    "detect_unit_mismatch",
    "extract_numbers",
    "verify_note",
]
