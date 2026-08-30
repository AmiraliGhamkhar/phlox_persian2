import tiktoken


# Count the number of tokens in each page_content
def openai_token_count(string: str) -> int:
    """Returns the number of tokens in a text string.

    Falls back to a character-based estimate when tiktoken cannot provide an
    encoding — including transient failures (e.g. the encoding file must be
    downloaded on first use and the host is offline), not only a missing
    package.
    """
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        num_tokens = len(encoding.encode(string, disallowed_special=()))
        return num_tokens
    except (ImportError, ValueError, OSError):
        # Fallback to character count when tiktoken is unavailable.
        # Use a rough approximation: 1 token ~ 4 characters.
        return len(string) // 4
