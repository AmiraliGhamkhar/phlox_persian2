"""Registry of the prompt keys stored in ``DEFAULT_PROMPTS["prompts"]``.

The config manager seeds ``DEFAULT_PROMPTS`` into the database and
``get_prompts_and_options()`` returns both ``prompts`` and ``options``. Only
``options`` is consumed at runtime; every prompt key below is currently
*legacy/unused* by the simplified three-page app:

* the live report path builds its system prompt from
  ``server.nlp_tools.report.REPORT_SYSTEM_PROMPT`` — it does not read the
  ``"report"`` database key;
* the chat/refinement/summary/letter/reasoning/job_extraction keys belong to
  the earlier full application and are kept for configuration compatibility.

The registry exists so that (a) each stored prompt key has a documented
owner/status, and (b) ``server/tests/test_prompt_registry.py`` fails if a new
key is added to ``DEFAULT_PROMPTS["prompts"]`` without a registry entry —
the usual way an unreviewed prompt silently enters the system.
"""

from __future__ import annotations

PROMPT_REGISTRY: dict[str, dict[str, str]] = {
    "refinement": {
        "status": "unused",
        "used_by": "legacy refinement path (not called by the workspace app)",
        "review": "text-editing assistant; no clinical decision making",
    },
    "chat": {
        "status": "unused",
        "used_by": "legacy chat assistant (not called by the workspace app)",
        "review": "informational chat for licensed professionals; non-diagnostic",
    },
    "summary": {
        "status": "unused",
        "used_by": "legacy one-sentence summary (not called by the workspace app)",
        "review": "must start with age/sex; under 20 words",
    },
    "letter": {
        "status": "unused",
        "used_by": "legacy medical letter writer (not called by the workspace app)",
        "review": "keeps names, drugs, doses, identifiers verbatim",
    },
    "reasoning": {
        "status": "unused",
        "used_by": "legacy case-review assistant (not called by the workspace app)",
        "review": "education-only; explicit 'not a decision support tool' guardrails",
    },
    "report": {
        "status": "unused",
        "used_by": "legacy report prompt; the live workspace report path uses "
        "server.nlp_tools.report.REPORT_SYSTEM_PROMPT instead",
        "review": "kept for config compatibility; do not extend it (edit REPORT_SYSTEM_PROMPT)",
    },
    "job_extraction": {
        "status": "unused",
        "used_by": "legacy PLAN -> task list extractor (not called by the workspace app)",
        "review": "structured JSON actions/exclusions; keeps doses verbatim",
    },
}
