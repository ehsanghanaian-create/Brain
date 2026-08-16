"""Run the MCP server manually (stdio) — mainly for debugging. Claude Desktop launches mcp/server.py directly.

    python scripts/run-mcp.py
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[1] / "mcp" / "server.py"), run_name="__main__")
