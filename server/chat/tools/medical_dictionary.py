"""search_medical_dictionary tool — bilingual Persian-English term lookup.

Deterministic (no LLM, no network): fuzzy-matches the clinician's query
against the curated medical terminology bundled in the app and returns the
best Persian/English pairs so the assistant can answer "what does this term
mean?" / translation questions with a stable, authoritative vocabulary.
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from server.chat.streaming.response import end_message, status_message, tool_response_message
from server.data.medical_dictionary import format_lookup_results, search

logger = logging.getLogger(__name__)


async def execute(
    tool_call: dict[str, Any],
    _llm_client,
    _config: dict[str, Any],
    message_list: list,
    _context_question_options: dict[str, Any],
) -> AsyncGenerator[dict[str, Any], None]:
    """Execute the search_medical_dictionary tool."""
    logger.info("Executing search_medical_dictionary tool...")
    yield status_message("Searching the medical terminology dictionary...")

    function_arguments: dict[str, Any] = {}
    if "arguments" in tool_call["function"]:
        try:
            if isinstance(tool_call["function"]["arguments"], str):
                function_arguments = json.loads(tool_call["function"]["arguments"])
            else:
                function_arguments = tool_call["function"]["arguments"]
        except json.JSONDecodeError:
            logger.error("Failed to parse function arguments JSON")

    term = function_arguments.get("term")
    limit = function_arguments.get("limit", 8)

    if not term or not str(term).strip():
        result_content = "Error: Please provide a medical term (Persian or English) to look up."
    else:
        try:
            matches = search(str(term), limit=min(int(limit), 20))
            result_content = format_lookup_results(str(term).strip(), matches)
        except Exception as e:  # noqa: BLE001 - a lookup failure must not kill the turn
            logger.error(f"Medical dictionary lookup error: {e}")
            result_content = f"Error searching the medical dictionary: {e}"

    message_list.append(
        tool_response_message(
            tool_call_id=tool_call.get("id", ""),
            content=result_content,
        )
    )
    yield end_message(function_response={"content": result_content, "citations": []})
