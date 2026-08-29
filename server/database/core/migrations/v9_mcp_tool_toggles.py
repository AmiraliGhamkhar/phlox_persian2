"""Migration v9: per-server disabled MCP tools.

mcp_servers.disabled_tools (JSON array of tool names) lets the clinician
vet and disable individual tools an external MCP server exposes, instead of
trusting every tool description the server advertises (ASI02 / LLM04:2026).
"""


def migrate(cursor, _db):
    """Add mcp_servers.disabled_tools (list of disabled tool names)."""
    cursor.execute("ALTER TABLE mcp_servers ADD COLUMN disabled_tools TEXT NOT NULL DEFAULT '[]'")
