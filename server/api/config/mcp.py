"""MCP server configuration API endpoints."""

import logging

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from server.database.config.mcp_manager import mcp_config_manager

router = APIRouter()


class McpServerCreate(BaseModel):
    """Schema for creating a new MCP server."""

    name: str
    url: str
    allow_sensitive_data: bool = False
    description: str = ""
    server_version: str = ""


class McpServerUpdate(BaseModel):
    """Schema for updating an MCP server."""

    name: str | None = None
    url: str | None = None
    allow_sensitive_data: bool | None = None
    description: str | None = None
    server_version: str | None = None
    disabled_tools: list[str] | None = None


class McpToolToggle(BaseModel):
    """Request body for enabling/disabling a single tool of a server."""

    tool_name: str
    disabled: bool


async def _refresh_tools_cache() -> None:
    """Best-effort refresh of the in-memory MCP tools cache."""
    try:
        from server.mcp.client import refresh_mcp_tools_cache

        await refresh_mcp_tools_cache()
    except ImportError:
        logging.info("MCP extra not installed; tools cache not refreshed")
    except Exception:
        logging.warning("MCP tools cache refresh failed", exc_info=True)


@router.get("/mcp")
def list_mcp_servers():
    """List all configured MCP servers."""
    servers = mcp_config_manager.get_servers()
    return JSONResponse(content={"servers": servers})


@router.get("/mcp/enabled")
def list_enabled_mcp_servers():
    """List only enabled MCP servers."""
    servers = mcp_config_manager.get_enabled_servers()
    return JSONResponse(content={"servers": servers})


@router.get("/mcp/cached-tools")
def list_cached_mcp_tools():
    """List tools from the last MCP tools-cache refresh, grouped by server.

    Lets the settings UI show the human exactly which tool names/descriptions
    an attached server exposes so they can be vetted and toggled.

    Registered before ``/mcp/{server_id}`` so ``cached-tools`` is not parsed
    as an integer id (which would 422).
    """
    try:
        from server.mcp.client import get_mcp_tools_sync
    except ImportError:
        return JSONResponse(content={"tools": []})

    tools = []
    for tool in get_mcp_tools_sync():
        function = tool.get("function", {})
        tools.append(
            {
                "name": function.get("name", ""),
                "description": function.get("description", ""),
                "server_id": tool.get("_mcp_server_id"),
                "server_tool_name": tool.get("_mcp_tool_name"),
                "requires_confirmation": bool(tool.get("_mcp_requires_confirmation")),
            }
        )
    return JSONResponse(content={"tools": tools})


@router.post("/mcp/refresh-tools")
async def refresh_mcp_tools():
    """Refresh the global MCP tools cache.

    This should be called after adding/removing MCP servers.
    """
    await _refresh_tools_cache()
    return JSONResponse(content={"message": "MCP tools cache refreshed"})


@router.get("/mcp/{server_id}")
def get_mcp_server(server_id: int):
    """Get a specific MCP server by ID."""
    server = mcp_config_manager.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return JSONResponse(content=server)


@router.post("/mcp")
async def add_mcp_server(data: McpServerCreate):
    """Add a new MCP server configuration."""
    try:
        server = mcp_config_manager.add_server(
            name=data.name,
            url=data.url,
            allow_sensitive_data=data.allow_sensitive_data,
            description=data.description,
            server_version=data.server_version,
        )
        await _refresh_tools_cache()
        return JSONResponse(content={"message": "MCP server added successfully", "server": server})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to add MCP server") from e


@router.put("/mcp/{server_id}")
async def update_mcp_server(server_id: int, data: McpServerUpdate):
    """Update an existing MCP server configuration."""
    server = mcp_config_manager.update_server(
        server_id=server_id,
        name=data.name,
        url=data.url,
        allow_sensitive_data=data.allow_sensitive_data,
        description=data.description,
        server_version=data.server_version,
        disabled_tools=data.disabled_tools,
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if data.name is not None or data.url is not None:
        await _refresh_tools_cache()
    return JSONResponse(content={"message": "MCP server updated successfully", "server": server})


@router.delete("/mcp/{server_id}")
async def delete_mcp_server(server_id: int):
    """Delete an MCP server configuration."""
    success = mcp_config_manager.remove_server(server_id)
    if not success:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await _refresh_tools_cache()
    return JSONResponse(content={"message": "MCP server deleted successfully"})


@router.post("/mcp/{server_id}/toggle")
async def toggle_mcp_server(server_id: int, enabled: bool = Body(..., embed=True)):
    """Enable or disable an MCP server."""
    success = mcp_config_manager.toggle_server(server_id, enabled)
    if not success:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await _refresh_tools_cache()
    return JSONResponse(
        content={"message": f"MCP server {'enabled' if enabled else 'disabled'} successfully"}
    )


@router.post("/mcp/{server_id}/tools/toggle")
def toggle_mcp_tool(server_id: int, payload: McpToolToggle):
    """Enable or disable a single tool exposed by an MCP server.

    Disabled tools are removed from the model's tool list and rejected at
    execution time, so a vetted server can be used without trusting every
    tool it advertises.
    """
    server = mcp_config_manager.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    disabled = set(server.get("disabled_tools") or [])
    if payload.disabled:
        disabled.add(payload.tool_name)
    else:
        disabled.discard(payload.tool_name)

    updated = mcp_config_manager.update_server(server_id, disabled_tools=sorted(disabled))
    return JSONResponse(
        content={
            "message": f"Tool '{payload.tool_name}' "
            f"{'disabled' if payload.disabled else 'enabled'}",
            "disabled_tools": updated.get("disabled_tools", []) if updated else [],
        }
    )


@router.post("/mcp/{server_id}/test")
async def test_mcp_server(server_id: int):
    """Test connection to an MCP server and list its tools.

    Returns the server's tools and server info if connection is successful.
    Also updates the server's stored description/version from the server's info.
    """
    from server.mcp.client import McpServerClient

    server_config = mcp_config_manager.get_server(server_id)
    if not server_config:
        raise HTTPException(status_code=404, detail="MCP server not found")

    client = McpServerClient(server_config)
    try:
        connected = await client.connect()
        if not connected:
            return JSONResponse(
                content={
                    "success": False,
                    "message": "Failed to connect to MCP server",
                    "tools": [],
                    "server_info": None,
                },
                status_code=400,
            )

        tools = await client.list_tools()
        server_info = client.get_server_info()

        # Update server with discovered info if available
        if server_info:
            description = f"{server_info.get('name', '')} - {len(tools)} tools available"
            server_version = server_info.get("version", "")
            mcp_config_manager.update_server(
                server_id,
                description=description,
                server_version=server_version,
            )

        await _refresh_tools_cache()

        return JSONResponse(
            content={
                "success": True,
                "message": "Connected successfully",
                "tools": tools,
                "server_info": server_info,
            }
        )
    except Exception as e:
        logging.error(f"Error connecting to MCP server: {e}", exc_info=True)
        return JSONResponse(
            content={
                "success": False,
                "message": "An internal error occurred while connecting to the MCP server.",
                "tools": [],
                "server_info": None,
            },
            status_code=500,
        )
    finally:
        await client.disconnect()
