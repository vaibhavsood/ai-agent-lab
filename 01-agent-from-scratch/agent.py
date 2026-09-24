"""
Agent #1: an AI agent from scratch.

No frameworks. Just: an LLM + some tools + a loop.

    python agent.py "Which files here mention 'root squash' and what do they do?"
    python agent.py --root C:/path/to/some/repo "Summarize how config is loaded"

The agent can only READ files under --root. Writing files and running
commands come in stage 02, together with human approval.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

MODEL = "claude-opus-5"
MAX_STEPS = 15  # safety net: stop runaway loops

# --------------------------------------------------------------------------
# 1. TOOLS: plain Python functions. The LLM never runs these itself;
#    it only *asks* us to, and we decide whether and how.
# --------------------------------------------------------------------------

ROOT = Path(".").resolve()


def _safe_path(rel: str) -> Path:
    """Resolve a path and refuse anything outside ROOT."""
    p = (ROOT / rel).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError(f"Path '{rel}' is outside the allowed root")
    return p


def list_files(path: str = ".") -> str:
    base = _safe_path(path)
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv")]
        for f in filenames:
            out.append(str(Path(dirpath, f).relative_to(ROOT)))
        if len(out) > 500:
            out.append("... (truncated at 500 files)")
            break
    return "\n".join(out) or "(no files)"


def read_file(path: str) -> str:
    text = _safe_path(path).read_text(encoding="utf-8", errors="replace")
    if len(text) > 50_000:
        return text[:50_000] + f"\n... (truncated; file is {len(text)} chars)"
    return text


def search_files(query: str) -> str:
    hits = []
    for rel in list_files(".").splitlines():
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if query.lower() in line.lower():
                    hits.append(f"{rel}:{n}: {line.strip()[:200]}")
        except OSError:
            continue
        if len(hits) >= 100:
            hits.append("... (truncated at 100 matches)")
            break
    return "\n".join(hits) or f"No matches for '{query}'"


TOOL_FUNCTIONS = {"list_files": list_files, "read_file": read_file, "search_files": search_files}

# --------------------------------------------------------------------------
# 2. TOOL SCHEMAS: how the LLM learns the tools exist. The description is
#    effectively the tool's "user interface" for the model.
# --------------------------------------------------------------------------

TOOLS = [
    {
        "name": "list_files",
        "description": "List all files (recursively) under a directory, relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory to list. Defaults to '.'"}},
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "Read the full text of one file. Use after list_files or search_files has told you the path.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path relative to the project root"}},
            "required": ["path"],
        },
    },
    {
        "name": "search_files",
        "description": "Case-insensitive text search across all files. Returns 'path:line: text' for each match.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Text to search for"}},
            "required": ["query"],
        },
    },
]

SYSTEM = (
    "You are a careful code and file investigation agent. "
    "Use the tools to find evidence before answering. "
    "Cite file paths and line numbers in your final answer."
)

# --------------------------------------------------------------------------
# 3. THE AGENT LOOP: the part that makes this an agent and not a chatbot.
#    LLM -> tool call -> observation -> LLM -> ... -> final answer
# --------------------------------------------------------------------------


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Execute one tool. Returns (result_text, is_error)."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"Unknown tool: {name}", True
    try:
        return fn(**args), False
    except Exception as e:  # errors go back to the model so it can recover
        return f"{type(e).__name__}: {e}", True


def run_agent(task: str) -> str:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    messages = [{"role": "user", "content": task}]  # this list IS the agent's state

    for step in range(1, MAX_STEPS + 1):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
            # If Opus 5 declines a request, retry it server-side on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

        # Keep the full assistant turn (text, thinking, tool_use) in history.
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "text" and block.text.strip() and response.stop_reason == "tool_use":
                print(f"\n[step {step}] model says: {block.text.strip()}")

        if response.stop_reason == "end_turn":
            return "".join(b.text for b in response.content if b.type == "text")
        if response.stop_reason == "refusal":
            return "The model declined this request."
        if response.stop_reason == "max_tokens":
            return "Stopped: the response hit max_tokens."
        if response.stop_reason != "tool_use":
            return f"Stopped with unexpected stop_reason: {response.stop_reason}"

        # The model asked for one or more tools. Run them all, then send every
        # result back in ONE user message.
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"[step {step}] tool call: {block.name}({json.dumps(block.input)})")
            output, is_error = run_tool(block.name, block.input)
            preview = output if len(output) < 300 else output[:300] + "..."
            print(f"[step {step}] result{' (ERROR)' if is_error else ''}: {preview}")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,  # links this result to the request
                "content": output,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})

    return f"Stopped: reached MAX_STEPS ({MAX_STEPS}) without a final answer."


def main():
    global ROOT
    parser = argparse.ArgumentParser(description="Agent #1: a from-scratch file investigation agent")
    parser.add_argument("task", help="What you want the agent to do")
    parser.add_argument("--root", default=".", help="Directory the agent may read (default: current dir)")
    args = parser.parse_args()

    ROOT = Path(args.root).resolve()
    print(f"Task: {args.task}\nRoot: {ROOT}")
    try:
        answer = run_agent(args.task)
    except anthropic.AuthenticationError:
        sys.exit("Authentication failed. Set ANTHROPIC_API_KEY (see README.md).")
    except anthropic.APIConnectionError:
        sys.exit("Network error: could not reach the Anthropic API.")
    print("\n=== FINAL ANSWER ===\n" + answer)


if __name__ == "__main__":
    main()
