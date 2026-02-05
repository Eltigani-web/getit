"""MCP server module for getit.

Exposes download functionality via the Model Context Protocol (MCP).
"""

from getit.mcp.server import create_server, main, mcp

__all__ = ["create_server", "main", "mcp"]
