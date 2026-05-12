"""
mcp.py — Optional MCP (Model Context Protocol) tool loader.

Loads MCP server tools when enabled in settings.
Requires: pip install langchain-mcp-adapters mcp
"""

import logging

logger = logging.getLogger(__name__)


def load_mcp_tools(mcp_servers: dict) -> list:
    """
    Load tools from configured MCP servers.
    Returns an empty list if MCP is not installed or no servers are enabled.
    """
    enabled = {name: cfg for name, cfg in mcp_servers.items() if cfg.get("enabled")}
    if not enabled:
        return []

    try:
        from langchain_mcp_adapters.tools import load_mcp_tools as _load
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        logger.warning("MCP servers configured but langchain-mcp-adapters is not installed. "
                       "Run: pip install langchain-mcp-adapters mcp")
        return []

    tools = []
    for name, cfg in enabled.items():
        try:
            server_params = StdioServerParameters(
                command=cfg["command"],
                args=cfg.get("args", []),
                env=cfg.get("env"),
            )
            import asyncio
            async def _fetch(sp):
                async with stdio_client(sp) as (r, w):
                    async with ClientSession(r, w) as session:
                        await session.initialize()
                        return await _load(session)

            server_tools = asyncio.run(_fetch(server_params))
            tools.extend(server_tools)
            logger.info(f"MCP '{name}': loaded {len(server_tools)} tools")
        except Exception as e:
            logger.warning(f"MCP '{name}' failed to load: {e}")

    return tools
