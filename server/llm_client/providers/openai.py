"""OpenAI-compatible provider implementation."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _strict_compatible(schema: Any) -> bool:
    """Whether a JSON schema satisfies OpenAI structured-output strictness:
    every object node declares additionalProperties=false (or none) and lists
    all of its properties as required. Recurses through properties/items/
    additionalProperties/anyOf."""
    if not isinstance(schema, dict):
        return True
    typ = schema.get("type")
    if typ == "object" or "properties" in schema:
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        if not set(props.keys()) <= required:
            return False
        if schema.get("additionalProperties", False) is not False:
            if isinstance(schema.get("additionalProperties"), dict):
                # OpenAI strict allows typed additionalProperties (maps).
                pass
            elif "additionalProperties" not in schema:
                return False
        for sub in list(props.values()) + (
            [schema["additionalProperties"]]
            if isinstance(schema.get("additionalProperties"), dict)
            else []
        ):
            if not _strict_compatible(sub):
                return False
    if isinstance(schema.get("items"), dict) and not _strict_compatible(schema["items"]):
        return False
    # Referenced sub-schemas must be strict too, not just the inline tree.
    for sub_schema in schema.get("$defs", {}).values():
        if not _strict_compatible(sub_schema):
            return False
    return all(_strict_compatible(alt) for alt in schema.get("anyOf", []) + schema.get("oneOf", []))


async def openai_compatible_chat(
    client,
    model: str,
    messages: list[dict[str, Any]],
    format: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
    extra_body: dict[str, Any] | None = None,
):
    """
    Send chat request to OpenAI-compatible API using the OpenAI client.

    Returns either a dict (non-streaming) or an async generator (streaming).
    """
    try:
        # Prepare parameters for OpenAI
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        if tools:
            params["tools"] = tools
            # Only force tool choice to required if explicitly specified
            if options and options.get("force_tools", False):
                params["tool_choice"] = "required"

        # Map options from our format to OpenAI format
        if options:
            # Direct mappings
            if "temperature" in options:
                params["temperature"] = options["temperature"]
            # Handle stop tokens
            if "stop" in options:
                params["stop"] = options["stop"]

        # Handle format (for JSON responses)
        if format:
            schema_name = format.get("title", "response")
            json_schema: dict[str, Any] = {
                "name": schema_name,
                "schema": format,
            }
            # Strict mode (plan ref B5) makes OpenAI-compatible endpoints
            # reject any key our grammar does not define, which is exactly
            # the class of drift ("helpful" extra fields, renamed keys) that
            # corrupts downstream processing. Schemas that are not strict-
            # compatible (optional keys, permissive objects) keep the old
            # non-strict behaviour so providers are never broken.
            if _strict_compatible(format):
                json_schema["strict"] = True
            params["response_format"] = {
                "type": "json_schema",
                "json_schema": json_schema,
            }

        # Add stream parameter if needed
        if stream:
            # Don't apply extra_body to streaming requests
            pass
            params["stream"] = stream

            # For streaming, return an async generator
            async def response_generator():
                reasoning_started = False
                async for chunk in await client.chat.completions.create(**params):
                    # Format the response to match Ollama's format
                    if hasattr(chunk, "choices") and chunk.choices:
                        delta = chunk.choices[0].delta
                        content = (
                            delta.content if hasattr(delta, "content") and delta.content else ""
                        )

                        # Check for reasoning in the delta (only used for Chat streaming)
                        reasoning = (
                            getattr(delta, "reasoning", None)
                            or getattr(delta, "reasoning_content", None)
                            or getattr(delta, "thinking", None)
                        )

                        # Normalize reasoning to </think> tags for consistency
                        if reasoning:
                            if not reasoning_started:
                                # Inject opening think tag
                                yield {
                                    "model": model,
                                    "message": {
                                        "role": "assistant",
                                        "content": "<think>",
                                    },
                                }
                                reasoning_started = True

                            # Stream reasoning content
                            yield {
                                "model": model,
                                "message": {
                                    "role": "assistant",
                                    "content": reasoning,
                                },
                            }
                        # Check for tool calls in the delta
                        tool_calls = None
                        if hasattr(delta, "tool_calls") and delta.tool_calls:
                            tool_calls = delta.tool_calls

                        if (
                            (content or tool_calls) and reasoning_started
                        ):  # Close think tag if we transition to content or tool calls
                            yield {
                                "model": model,
                                "message": {
                                    "role": "assistant",
                                    "content": "</think>\n\n",
                                },
                            }
                            reasoning_started = False

                        response = {
                            "model": model,
                            "message": {
                                "role": "assistant",
                                "content": content,
                            },
                        }

                        # Add tool_calls if present
                        if tool_calls:
                            response["message"]["tool_calls"] = tool_calls

                        yield response

                # If stream ends while reasoning, close the tag
                if reasoning_started:
                    yield {
                        "model": model,
                        "message": {
                            "role": "assistant",
                            "content": "</think>\n\n",
                        },
                    }

            return response_generator()
        else:
            # Only apply extra_body to non-streaming requests as it seems to break some endpoints
            if extra_body:
                params.update(extra_body)
            response = await client.chat.completions.create(**params)
            # Convert to Ollama-like format for consistency
            content = response.choices[0].message.content or ""

            result = {
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
            }

            # Add reasoning to result if present
            reasoning = (
                getattr(response.choices[0].message, "reasoning", None)
                or getattr(response.choices[0].message, "reasoning_content", None)
                or getattr(response.choices[0].message, "thinking", None)
            )

            if reasoning:
                result["message"]["reasoning"] = reasoning

            # Add tool_calls if present
            if (
                hasattr(response.choices[0].message, "tool_calls")
                and response.choices[0].message.tool_calls
            ):
                result["message"]["tool_calls"] = []
                for tool_call in response.choices[0].message.tool_calls:
                    result["message"]["tool_calls"].append(
                        {
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                    )

            return result
    except Exception as e:
        from server.utils.http_retry import ProviderHTTPError, sanitize_provider_error

        status = getattr(e, "status_code", None)
        if status is None:
            status = getattr(getattr(e, "response", None), "status_code", None)
        body = sanitize_provider_error(
            str(getattr(e, "body", None) or getattr(e, "message", None) or e)
        )
        if status == 401:
            raise ProviderHTTPError(
                f"LLM authentication failed (401): {body}", status_code=status
            ) from e
        if status == 403:
            raise ProviderHTTPError(
                f"LLM request forbidden (403): {body}", status_code=status
            ) from e
        if status == 429:
            raise ProviderHTTPError(f"LLM rate limited (429): {body}", status_code=status) from e
        if status and int(status) >= 500:
            raise ProviderHTTPError(
                f"LLM provider error ({status}): {body}", status_code=status
            ) from e
        logger.error("Error in OpenAI-compatible chat request: %s", e)
        raise
