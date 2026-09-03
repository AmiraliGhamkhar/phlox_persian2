"""Hallucination-resistance benchmark for Phlox's ASR + note pipeline.

Two modes (see docs/phlox-accuracy-hallucination-plan.md, refs C1/C2):

* ``offline`` (default, CI-safe, zero third-party deps): replays the
  deterministic guards in ``server/transcription/verification.py`` and the
  artifact detector in ``server/transcription/hygiene.py`` against synthetic
  fixtures with *planted* failure modes (fabrication, number drift,
  negation flip, caption artifact) and fails unless every plant is caught —
  and unless every gold bullet passes (fixtures must be well-formed). These
  modules are loaded directly from source (they are stdlib-only), so this
  mode runs anywhere without the app's database or model stack.

* ``live``: runs the real extraction/refinement pipeline against the
  configured LLM and reports metrics — claim-support rate, fabrication,
  number/negation issues. Requires the full server environment; never used
  as a hard CI gate.

Run:
    python -m server.bench.run_bench --mode offline
    python -m server.bench.run_bench --mode live
"""

from .dataset import load_fixtures

__all__ = ["load_fixtures"]
