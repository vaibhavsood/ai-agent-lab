"""
The agent's side of MCP: start servers, discover their tools, call them.

The MCP SDK is async; the agent is plain synchronous code. Each server
connection therefore runs on its own background thread with its own event
loop, and the agent gets simple blocking methods: tools() and call().
"""

import asyncio
import json
import os
import sys
import threading
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class MCPServerConnection:
    def __init__(self, name: str, command: str, args: list[str], env: dict | None = None, cwd: str | None = None):
        self.name = name
        self.params = StdioServerParameters(command=command, args=args, cwd=cwd,
                                            env={**os.environ, **(env or {})})
        self.session = None
        self._tools = []
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stop = None
        self._error = None
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

    async def _serve(self):
        """Open the connection, then keep it open until close() is called."""
        try:
            async with stdio_client(self.params, errlog=sys.stderr) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._tools = (await session.list_tools()).tools
                    self.session = session
                    self._stop = asyncio.Event()
                    self._ready.set()
                    await self._stop.wait()
        except Exception as e:
            self._error = e
            self._ready.set()

    def start(self, timeout: float = 60) -> "MCPServerConnection":
        asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        if not self._ready.wait(timeout):
            raise TimeoutError(f"MCP server '{self.name}' didn't start within {timeout}s")
        if self._error:
            raise RuntimeError(f"MCP server '{self.name}' failed to start: {self._error}")
        return self

    def tools(self):
        return self._tools

    def call(self, tool: str, arguments: dict, timeout: float = 90) -> tuple[str, bool]:
        """Call one tool. Returns (text, is_error), like our own tools."""
        future = asyncio.run_coroutine_threadsafe(self.session.call_tool(tool, arguments), self._loop)
        result = future.result(timeout)
        text = "\n".join(getattr(c, "text", f"[{getattr(c, 'type', 'non-text')} content]") for c in result.content)
        return text, bool(result.is_error)

    def close(self):
        if self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)


def load_config(path: Path) -> dict:
    """Same shape as Claude Code's .mcp.json: {"mcpServers": {name: {command, args, env}}}."""
    if not path.exists():
        return {}
    servers = json.loads(path.read_text(encoding="utf-8")).get("mcpServers", {})
    base = path.parent
    for cfg in servers.values():  # let configs say "python" and relative paths
        if cfg.get("command") == "python":
            cfg["command"] = sys.executable
        cfg["args"] = [str((base / a).resolve()) if a.endswith(".py") else a for a in cfg.get("args", [])]
    return servers


def clean_schema(schema: dict) -> dict:
    """MCP servers may use JSON Schema keywords Gemini's function declarations reject; keep the basics."""
    keep = {"type", "description", "properties", "required", "items", "enum", "default",
            "minimum", "maximum", "format"}
    if not isinstance(schema, dict):
        return schema
    out = {}
    for k, v in schema.items():
        if k not in keep:
            continue
        if k == "properties":
            out[k] = {name: clean_schema(sub) for name, sub in v.items()}
        elif k == "items":
            out[k] = clean_schema(v)
        else:
            out[k] = v
    if out.get("type") == "object":
        out.setdefault("properties", {})
    return out
