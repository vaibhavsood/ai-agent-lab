"""
Agent #2b: stage 02, running on Gemini's free tier instead of Claude.

The tools, the approval gate and the loop's logic are the same as stage 02.
Only two things change: how tools are described to the model, and how we
call the model and read its reply. Compare this file side by side with
../02-tools-with-approval/agent.py.

    python agent.py --root C:/path/to/sandbox "Create hello.py that prints hi, then run it"

Free-tier data may be used by Google to improve its products, so only point
this at the lab or a sandbox folder, never at confidential code.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from google import genai

MODEL = "gemini-3.8-flash"  # free tier
MAX_STEPS = 15  # safety net: stop runaway loops

# --------------------------------------------------------------------------
# 1. TOOLS (identical to stage 02)
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

NEEDS_APPROVAL = {"write_file", "run_command"}

# --------------------------------------------------------------------------
# 2. TOOL SCHEMAS (CHANGED: Gemini's format)
#    Same names, descriptions and JSON Schema as stage 02. Only the wrapper
#    differs: Claude wants "input_schema", Gemini wants "type": "function"
#    and "parameters".
# --------------------------------------------------------------------------

SHELL = "Windows cmd.exe" if os.name == "nt" else "sh"


def _tool(name, description, properties, required):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


TOOLS = [
    _tool("list_files", "List all files (recursively) under a directory, relative to the project root.",
          {"path": {"type": "string", "description": "Directory to list. Defaults to '.'"}}, []),
    _tool("read_file", "Read the full text of one file. Use after list_files or search_files has told you the path.",
          {"path": {"type": "string", "description": "File path relative to the project root"}}, ["path"]),
    _tool("search_files", "Case-insensitive text search across all files. Returns 'path:line: text' for each match.",
          {"query": {"type": "string", "description": "Text to search for"}}, ["query"]),
    _tool("write_file",
          "Create or overwrite a file with the given content. Requires user approval. "
          "Read a file before overwriting it so you don't lose its contents.",
          {"path": {"type": "string", "description": "File path relative to the project root"},
           "content": {"type": "string", "description": "The complete new file content"}},
          ["path", "content"]),
    _tool("run_command",
          f"Run a shell command in the project root using {SHELL}. Requires user approval. "
          "Returns exit code, stdout and stderr. Times out after 60 seconds; don't start servers or interactive programs.",
          {"command": {"type": "string", "description": "The command line to run"}}, ["command"]),
]

SYSTEM = (
    "You are a careful agent that can investigate and change files in a project. "
    "Use the tools to find evidence before acting, and prefer the smallest change that does the job. "
    "write_file and run_command require the user's approval. If the user declines, "
    "do not retry the same action; adapt to their reason or ask what they want instead."
)

# --------------------------------------------------------------------------
# 3. HUMAN APPROVAL (identical to stage 02)
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


# --------------------------------------------------------------------------
# 4. THE AGENT LOOP (CHANGED: Gemini's call and reply shapes; same logic)
#
#    Claude                         Gemini Interactions API
#    messages=[...]                 input=[...]   (list of "steps")
#    tool_use block (id, input)     function_call step (id, arguments)
#    tool_result (tool_use_id)      function_result step (call_id)
#    stop_reason == "end_turn"      no function_call steps -> done
# --------------------------------------------------------------------------


def run_agent(task: str) -> str:
    client = genai.Client()  # reads GEMINI_API_KEY from the environment
    # This list IS the agent's state, exactly like `messages` in stage 02.
    history = [{"type": "user_input", "content": [{"type": "text", "text": task}]}]

    for step in range(1, MAX_STEPS + 1):
        interaction = client.interactions.create(
            model=MODEL,
            system_instruction=SYSTEM,
            tools=TOOLS,
            input=history,
            store=False,  # stateless: we resend the full history every call, like with Claude
        )

        if interaction.status in ("failed", "cancelled", "incomplete", "budget_exceeded"):
            return f"Stopped: interaction status was '{interaction.status}'."

        # Keep only the model's NEW steps: everything after the last input we sent.
        steps = interaction.steps or []
        last_input = max((i for i, s in enumerate(steps) if s.type in ("user_input", "function_result")), default=-1)
        new_steps = steps[last_input + 1:]
        history.extend(s.model_dump() for s in new_steps)

        calls = [s for s in new_steps if s.type == "function_call"]
        if not calls:
            return interaction.output_text or "(the model returned no text)"

        for s in new_steps:
            if s.type == "model_output" and calls:
                text = "".join(c.text for c in (s.content or []) if getattr(c, "type", None) == "text").strip()
                if text:
                    print(f"\n[step {step}] model says: {text}")

        # Run every requested tool, then send all results back together.
        for call in calls:
            args = call.arguments or {}
            print(f"[step {step}] tool call: {call.name}({json.dumps(args)[:200]})")
            output, is_error = run_tool(call.name, args)
            preview = output if len(output) < 300 else output[:300] + "..."
            print(f"[step {step}] result{' (ERROR)' if is_error else ''}: {preview}")
            history.append({
                "type": "function_result",
                "call_id": call.id,  # links this result to the request
                "name": call.name,
                "result": output,
                "is_error": is_error,
            })

    return f"Stopped: reached MAX_STEPS ({MAX_STEPS}) without a final answer."


def main():
    global ROOT
    parser = argparse.ArgumentParser(description="Agent #2b: stage 02 on Gemini's free tier")
    parser.add_argument("task", help="What you want the agent to do")
    parser.add_argument("--root", default=".", help="Directory the agent works in (default: current dir)")
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY is not set. See README.md, and open a NEW terminal after setting it.")

    ROOT = Path(args.root).resolve()
    print(f"Task: {args.task}\nRoot: {ROOT}\nModel: {MODEL}")
    try:
        answer = run_agent(args.task)
    except KeyboardInterrupt:
        sys.exit("\nStopped by user.")
    except Exception as e:
        # The Interactions API's error classes live in a private module, so we
        # read the HTTP status code instead of importing them.
        status = getattr(e, "status_code", None) or getattr(e, "code", None)
        if status is None:
            raise  # not an API error: a real bug, show the full traceback
        if "API key not valid" in str(e) or status in (401, 403):
            sys.exit(f"Gemini rejected the API key ({status}). Check GEMINI_API_KEY, then open a NEW terminal.")
        if status == 429:
            sys.exit("Free-tier rate limit reached. Wait a minute (or until tomorrow for the daily limit) and retry.")
        sys.exit(f"Gemini API error ({status}): {str(e)[:500]}")
    print("\n=== FINAL ANSWER ===\n" + answer)


if __name__ == "__main__":
    main()
