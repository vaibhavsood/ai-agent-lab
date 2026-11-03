# 07 - MCP (Model Context Protocol)

## Goal

Stop hand-writing every tool inside `agent.py`. Expose my tools as an MCP
**server** any agent can use, and make my agent an MCP **client** that
discovers tools from servers at startup.

## What I learned

- **MCP is a standard plug between agents and tools.** N agents + M tools
  instead of N × M integrations. Core messages: "list your tools" and
  "call this tool with these arguments".
- **An MCP tool is exactly a stage 01 tool** (name, description, JSON schema),
  except the description and code live in another program.
- **Server side** (`lab_server.py`): `@server.tool` turns a Python function into
  a tool; the SDK builds the JSON schema from the type hints.
- **stdio servers must keep stdout clean:** it carries the protocol. Logs go to stderr.
- **Client side:** start each server, `list_tools()`, convert the schemas for
  Gemini, route calls by name. The agent loop didn't change.
- **Trust:** a third-party server's descriptions talk directly to my model.
  The official fetch server's description tells the model to ignore earlier
  "no internet" instructions; harmless here, but that's the tool poisoning
  mechanism. Servers' "read-only" hints are self-reported; approval is based
  on MY config (`"readOnly": true`), not their claims.
- **SDKs move fast:** `mcp` 2.x renamed `FastMCP` to `MCPServer` and switched
  to snake_case fields (`input_schema`, `is_error`). Tutorials for 1.x break.

## Architecture

```
            ┌──────────────── my agent (MCP client) ────────────────┐
 you ──►    │ built-in tools: list/read/write/run_command, remember  │
            │ + discovered at startup from mcp_servers.json:         │
            └───────┬───────────────────────────────┬────────────────┘
                    │ stdio (JSON messages)          │ stdio
          ┌─────────▼──────────┐          ┌──────────▼─────────┐
          │ lab_server.py      │          │ mcp_server_fetch   │
          │ search_notes       │          │ fetch (web pages)  │
          │ read_note          │          │ (official server)  │
          └────────────────────┘          └────────────────────┘
   The same lab_server.py can also be plugged into Claude Code.
```

## Files

| File | What it is |
|---|---|
| `lab_server.py` | My MCP server: `search_notes`, `read_note` (refuses paths outside the lab and `memory.md`) |
| `mcp_client.py` | Connection bridge (async SDK → sync agent), config loader, schema cleaner |
| `mcp_servers.json` | Which servers to start; same format as Claude Code's `.mcp.json` |
| `agent.py` | Stage 06 + MCP tools; built-in `search_notes` removed (comes from the server now) |
| `test_server.py` | Talks to `lab_server.py` over real MCP (7 checks) |
| `test_mcp_client.py` | Discovery, routing, approval rules (6 checks) |

## Run

```powershell
cd C:\Users\temp1\claude-learn\ai-agent-lab\07-mcp
..\.venv\Scripts\python agent.py --root ..
..\.venv\Scripts\python test_server.py
..\.venv\Scripts\python test_mcp_client.py
```

## Experiments (2026-11-03)

| Question | What happened |
|---|---|
| What is tool poisoning? | `search_notes` (MCP) → `read_note` (MCP) whole PDF → answer, 1/1 citation verified |
| Fetch modelcontextprotocol.io, what is MCP? | `fetch` (MCP) → live page → 2-sentence answer, marked not-from-notes, URL named |

The fetched page contained text addressed to AI agents ("Use this file to
discover all available pages..."): web content can instruct agents too.

## Problems I encountered

- `mcp` 2.x API changes (see above). Read the installed package, not old tutorials.
- Installing the fetch server could have downgraded `mcp`; a `pip install --dry-run` showed it was compatible.
- Put `finally:` before an `except:` (syntax error); hidden because I'd suppressed stderr in the test run.

## What I would improve

- Add `read_only_hint` annotations to my own server's tools.
- Pin approved tool descriptions and warn if a server changes them later (rug-pull protection, stage 09).

## Check your understanding

1. What's the difference between an MCP tool and the tools in stage 01?
2. Why must a stdio MCP server never print to stdout?
3. Why base approval on my config instead of the server's `read_only_hint`?

## Next step

Stage 08: multi-agent.
