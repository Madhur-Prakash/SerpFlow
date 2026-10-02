"""The entry points this project ships, asserted to actually load.

Section 77: no fake implementations. The CLI, the MCP server and the SDKs are
documented surfaces, so they are covered here rather than assumed to work.

These are deliberately import-and-shape tests. They caught a real break: the
``mcp`` package renamed ``FastMCP`` to ``MCPServer`` in 2.x, and nothing else
in the suite imports ``app.mcp.server``, so ``serpflow-mcp`` was failing at
startup while every other test passed.
"""

from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


# --------------------------------------------------------------------------
# MCP (section 59)
# --------------------------------------------------------------------------
def test_mcp_server_module_loads():
    """Importing it is the whole test. It is what `serpflow-mcp` does first."""
    import app.mcp.server as server

    assert server.mcp is not None
    assert server.mcp.name == "serpflow"


def test_mcp_exposes_the_documented_tools():
    import app.mcp.server as server

    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == {"plan", "search", "explain", "catalog"}


def test_mcp_tools_carry_descriptions():
    """An agent picks a tool by its description, so an empty one is a defect."""
    import app.mcp.server as server

    tools = asyncio.run(server.mcp.list_tools())
    for tool in tools:
        assert tool.description and len(tool.description) > 40, tool.name


# --------------------------------------------------------------------------
# CLI (section 60)
# --------------------------------------------------------------------------
def test_cli_exposes_the_documented_commands():
    from app.cli.main import app as cli

    names = {command.name or command.callback.__name__ for command in cli.registered_commands}
    assert {"plan", "search", "replay", "runs", "health", "version"} <= names


def test_cli_exposes_the_documented_groups():
    from app.cli.main import app as cli

    groups = {group.name for group in cli.registered_groups}
    assert {"catalog", "benchmark", "cache"} <= groups


# --------------------------------------------------------------------------
# SDKs (section 58)
# --------------------------------------------------------------------------
def test_sdk_is_importable_as_serpflow():
    """The docs say `from serpflow import SerpFlow`. That has to be true."""
    from serpflow import AsyncSerpFlow, SerpApiCompat, SerpFlow

    assert SerpFlow is not None
    assert AsyncSerpFlow is not None
    assert SerpApiCompat is not None


@pytest.mark.parametrize(
    "method", ["plan", "route", "search", "run", "stream", "explain", "runs", "replay", "health"]
)
def test_sync_sdk_has_the_documented_methods(method):
    from serpflow import SerpFlow

    assert callable(getattr(SerpFlow, method, None)), method


@pytest.mark.parametrize("method", ["plan", "route", "search", "run", "stream"])
def test_async_sdk_has_the_documented_methods(method):
    from serpflow import AsyncSerpFlow

    assert callable(getattr(AsyncSerpFlow, method, None)), method


def test_serpapi_compat_keeps_the_upstream_shape():
    """Existing SerpApi code calls get_dict()/get_json(). Renaming is a break."""
    from serpflow import SerpApiCompat

    assert callable(SerpApiCompat.get_dict)
    assert callable(SerpApiCompat.get_json)


def test_sdk_error_is_exported():
    from serpflow import SerpFlowError

    assert issubclass(SerpFlowError, Exception)


# --------------------------------------------------------------------------
# Packaging
# --------------------------------------------------------------------------
def test_console_scripts_point_at_real_callables():
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = config["project"]["scripts"]
    assert scripts["serpflow"] == "app.cli.main:app"
    assert scripts["serpflow-mcp"] == "app.mcp.server:main"

    import app.mcp.server as server
    from app.cli.main import app as cli

    assert cli is not None
    assert callable(server.main)


def test_license_is_apache_2_0():
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "Apache-2.0" in text
    assert config["project"]["name"] == "serpflow"
