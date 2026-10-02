"""MCP server exposing search, plan, explain and catalog on the same service layer."""

from app.mcp.server import main, mcp

__all__ = ["main", "mcp"]
