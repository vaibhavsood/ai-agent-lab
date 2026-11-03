"""
Offline tests for the agent's MCP client side. Starts the real lab_server.py.
No Gemini calls (read_note only).

    python test_mcp_client.py
"""

import builtins
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agent
import mcp_client


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    if not cond:
        agent.close_mcp()
        sys.exit(1)


def config(read_only: bool) -> Path:
    p = Path(tempfile.mkdtemp()) / "mcp_servers.json"
    p.write_text(json.dumps({"mcpServers": {"lab-notes": {
        "command": "python", "args": [str(HERE / "lab_server.py")], "readOnly": read_only}}}))
    return p


# 1. schema cleaning keeps what Gemini accepts, drops the rest
raw = {"type": "object", "title": "Args", "$defs": {}, "additionalProperties": False,
       "properties": {"url": {"type": "string", "format": "uri", "title": "Url"}}, "required": ["url"]}
check("clean_schema drops title/$defs/additionalProperties",
      mcp_client.clean_schema(raw) == {"type": "object", "properties": {"url": {"type": "string", "format": "uri"}},
                                       "required": ["url"]})

# 2. discovery: connecting adds the server's tools next to the built-in ones
builtin = {t["name"] for t in agent.TOOLS}
agent.connect_mcp(config(read_only=True))
names = {t["name"] for t in agent.TOOLS}
check("search_notes and read_note were discovered from the server", {"search_notes", "read_note"} <= names - builtin)
check("their descriptions say where they come from",
      all(t["description"].startswith("[from MCP server 'lab-notes']") for t in agent.TOOLS if t["name"] in agent.MCP_TOOLS))

# 3. calls are routed to the server process; readOnly in MY config = no approval
builtins.input = lambda prompt="": (_ for _ in ()).throw(AssertionError("should not ask"))
out, err = agent.run_tool("read_note", {"path": "knowledge/agent-concepts.md"})
check("read_note runs on the MCP server without approval", not err and "Tool descriptions" in out)
agent.close_mcp()

# 4. without readOnly in MY config, approval is required, even though the server's tools are harmless
agent.MCP_TOOLS.clear()
agent.TOOLS[:] = [t for t in agent.TOOLS if t["name"] in builtin]
agent.connect_mcp(config(read_only=False))
answers_given = iter(["n", "just testing"])
builtins.input = lambda prompt="": next(answers_given)
out, err = agent.run_tool("read_note", {"path": "knowledge/agent-concepts.md"})
check("an untrusted server's tool needs approval, and a 'no' blocks it", err and "declined" in out and "just testing" in out)
agent.close_mcp()

print("\nAll MCP client checks passed.")
