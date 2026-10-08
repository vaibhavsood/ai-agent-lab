"""
Agent #2: tools with side effects + human approval.

Same loop as stage 01, plus two tools that CHANGE things: write_file and
run_command. Before either runs, the agent shows you exactly what it wants
to do and waits for your y/n. A "no" (with an optional reason) goes back to
the model as a tool result, so it can adapt.

    python agent.py --root C:/path/to/sandbox "Create hello.py that prints hi, then run it"

Use a throwaway folder as --root while experimenting.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import anthropic

MODEL = "claude-opus-5"
MAX_STEPS = 15  # safety net: stop runaway loops

# --------------------------------------------------------------------------
# 1. TOOLS
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


# NEW in stage 02: tools with side effects


def write_file(path: str, content: str) -> str:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}"


def run_command(command: str) -> str:
    # NOTE: the path sandbox does NOT apply here. A command can touch anything
    # your user account can. Human approval is the only guard.
    result = subprocess.run(command, shell=True, cwd=ROOT, capture_output=True, text=True, timeout=60)
    out = f"exit code: {result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    return out if len(out) < 20_000 else out[:20_000] + "\n... (truncated)"


TOOL_FUNCTIONS = {
    "list_files": list_files,
    "read_file": read_file,
    "search_files": search_files,
    "write_file": write_file,
    "run_command": run_command,
}

# Tools that change the world need a human "yes" first.
NEEDS_APPROVAL = {"write_file", "run_command"}

# --------------------------------------------------------------------------
# 2. TOOL SCHEMAS
# --------------------------------------------------------------------------

SHELL = "Windows cmd.exe" if os.name == "nt" else "sh"

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
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a file with the given content. Requires user approval. "
            "Read a file before overwriting it so you don't lose its contents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to the project root"},
                "content": {"type": "string", "description": "The complete new file content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_command",
        "description": (
            f"Run a shell command in the project root using {SHELL}. Requires user approval. "
            "Returns exit code, stdout and stderr. Times out after 60 seconds; don't start servers or interactive programs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "The command line to run"}},
            "required": ["command"],
        },
    },
]

SYSTEM = (
    "You are a careful agent that can investigate and change files in a project. "
    "Use the tools to find evidence before acting, and prefer the smallest change that does the job. "
    "write_file and run_command require the user's approval. If the user declines, "
    "do not retry the same action; adapt to their reason or ask what they want instead."
)

# --------------------------------------------------------------------------
# 3. HUMAN APPROVAL (new in stage 02)
# --------------------------------------------------------------------------


def ask_approval(name: str, args: dict) -> tuple[bool, str]:
    """Show the human exactly what the agent wants to do. Returns (approved, reason)."""
    if name == "write_file":
        target = _safe_path(args.get("path", ""))  # refuse bad paths before asking
    print("\n" + "=" * 60)
    if name == "write_file":
        content = args.get("content", "")
        lines = content.splitlines()
        action = "OVERWRITE existing file" if target.exists() else "create new file"
        print(f"The agent wants to {action}: {args.get('path')}  ({len(lines)} lines)")
        print("-" * 60)
        print("\n".join(lines[:20]) + (f"\n... ({len(lines) - 20} more lines)" if len(lines) > 20 else ""))
    elif name == "run_command":
        print(f"The agent wants to run this command in {ROOT}:")
        print(f"  > {args.get('command')}")
    print("=" * 60)

    answer = input("Allow? (y/n): ").strip().lower()
    if answer in ("y", "yes"):
        return True, ""
    reason = input("Reason, sent to the agent (optional, Enter to skip): ").strip()
    return False, reason


# --------------------------------------------------------------------------
# 4. THE AGENT LOOP: unchanged from stage 01, except run_tool's approval check
# --------------------------------------------------------------------------


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Execute one tool. Returns (result_text, is_error)."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"Unknown tool: {name}", True
    try:
        if name in NEEDS_APPROVAL:
            approved, reason = ask_approval(name, args)
            if not approved:
                msg = "The user declined this action."
                return (msg + f" Their reason: {reason}" if reason else msg), True
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

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"[step {step}] tool call: {block.name}({json.dumps(block.input)[:200]})")
            output, is_error = run_tool(block.name, block.input)
            preview = output if len(output) < 300 else output[:300] + "..."
            print(f"[step {step}] result{' (ERROR)' if is_error else ''}: {preview}")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})

    return f"Stopped: reached MAX_STEPS ({MAX_STEPS}) without a final answer."


def main():
    global ROOT
    parser = argparse.ArgumentParser(description="Agent #2: file agent that can write and run commands, with approval")
    parser.add_argument("task", help="What you want the agent to do")
    parser.add_argument("--root", default=".", help="Directory the agent works in (default: current dir)")
    args = parser.parse_args()

    ROOT = Path(args.root).resolve()
    print(f"Task: {args.task}\nRoot: {ROOT}")
    try:
        answer = run_agent(args.task)
    except anthropic.AuthenticationError:
        sys.exit("Authentication failed. Set ANTHROPIC_API_KEY (see README.md).")
    except anthropic.APIConnectionError:
        sys.exit("Network error: could not reach the Anthropic API.")
    except KeyboardInterrupt:
        sys.exit("\nStopped by user.")
    print("\n=== FINAL ANSWER ===\n" + answer)


if __name__ == "__main__":
    main()
