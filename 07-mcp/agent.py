"""
Agent #7: the stage 06 agent as an MCP CLIENT.

New in this stage: tools can come from MCP servers listed in mcp_servers.json
(same format as Claude Code's .mcp.json). At startup the agent starts each
server, DISCOVERS its tools, and offers them to the model next to its own.
search_notes is no longer built in: it comes from the lab-notes MCP server
(lab_server.py), and fetch (web pages) comes from the official fetch server.

    python agent.py --root ..
    python agent.py --root .. --no-mcp          # only the built-in tools

MCP tools need your approval unless YOU marked their server "readOnly" in
mcp_servers.json. A server's own "read-only" claim is shown, not trusted.

Below: stage 06's docstring, still accurate for everything else.

Agent #6: the stage 05 agent with STRUCTURED answers that code can verify.

New in this stage:
  1. Every final answer is JSON in a fixed schema (answers.ANSWER_SCHEMA):
     found_in_notes, answer, citations[{source, quote}]. The API enforces it.
  2. Code checks each citation: is the quote really in that file/lines/page?
     If not, the failures go back to the model for ONE fix (self-correction).
  3. Reasoning controls: --thinking minimal|low|medium|high, --show-thinking.

    python agent.py --root ..                          # uses stage 05's index.json
    python agent.py --root .. --thinking high --show-thinking

Below: stage 05's docstring, still accurate for everything else.

Agent #5: the stage 04 agent + RAG (a knowledge assistant for my notes).

New in this stage: search_notes(query), a tool that finds the passages most
similar IN MEANING to the query (via embeddings), each with a file:line
source the model must cite. Everything else is stage 04 unchanged.

    python index.py                # build index.json from the lab (once, and after notes change)
    python agent.py --root ..      # chat with your notes

Chat commands: /memory, /compact, /exit
Runs on Gemini's free tier: only index and point it at the lab or a sandbox.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

from google import genai

import answers
import mcp_client
import rag

# Free tier. The newest model (gemini-3.8-flash) was so queued on the free tier
# that even "2+2" took 100+ seconds; 3.6-flash answered in ~7s (measured 2026-10-26).
MODEL = "gemini-3.6-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"  # used when MODEL stops answering (free-tier availability varies)
MAX_STEPS = 15  # per user message
TIMEOUT_SECONDS = 45  # healthy free-tier models answer in 2-8s
MAX_RETRIES = 3
MEMORY_FILE = Path(__file__).parent / "memory.md"  # git-ignored: it's personal

ROOT = Path(".").resolve()

# --------------------------------------------------------------------------
# 1. TOOLS (from 02b, unchanged) + remember (new)
# --------------------------------------------------------------------------


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
            if f == "index.json":  # the RAG index: huge, machine-only; search_notes reads it instead
                continue
            out.append(str(Path(dirpath, f).relative_to(ROOT)))
        if len(out) > 500:
            out.append("... (truncated at 500 files)")
            break
    return "\n".join(out) or "(no files)"


def read_file(path: str) -> str:
    p = _safe_path(path)
    if p.suffix.lower() == ".pdf":  # PDFs are binary: extract the text, marking each page
        pages = rag.read_pdf_pages(p)
        if not any(t.strip() for t in pages):
            return f"{path}: {len(pages)} pages but no extractable text (scanned PDF?)"
        text = "\n\n".join(f"--- page {n} ---\n{t}" for n, t in enumerate(pages, 1))
    else:
        text = p.read_text(encoding="utf-8", errors="replace")
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
    # NOTE: the path sandbox does NOT apply here. Human approval is the only guard.
    result = subprocess.run(command, shell=True, cwd=ROOT, capture_output=True, text=True, timeout=60)
    out = f"exit code: {result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    return out if len(out) < 20_000 else out[:20_000] + "\n... (truncated)"


# NEW: long-term memory. A plain text file the model can append to.


def load_memory() -> str:
    return MEMORY_FILE.read_text(encoding="utf-8") if MEMORY_FILE.exists() else ""


def remember(fact: str) -> str:
    fact = " ".join(fact.split())  # one line per fact
    with MEMORY_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- {fact} ({date.today()})\n")
    print(f"[memory] saved: {fact}")
    return "Saved to long-term memory."


# NEW in stage 05: retrieval over the index built by index.py

# Same index format as stage 05, so reuse its index instead of re-embedding everything.
INDEX_FILE = Path(__file__).parent / "index.json"
if not INDEX_FILE.exists():
    INDEX_FILE = Path(__file__).resolve().parents[1] / "05-rag" / "index.json"

THINKING_LEVEL = None  # None = model default; or "minimal" | "low" | "medium" | "high"
SHOW_THINKING = False  # print the model's reasoning summaries
LAST_RESULT = None  # the last structured answer + its checks (used by compare_thinking.py)
INDEX = None  # loaded in main()
EMBED = None  # embedding function, set in main()


def search_notes(query: str, top_k: int = 5) -> str:
    if INDEX is None:
        return "There is no index yet. Tell the user to run: python index.py"
    return rag.format_results(rag.search(INDEX, query, EMBED, top_k=min(max(top_k, 1), 10)))


TOOL_FUNCTIONS = {
    "list_files": list_files,
    "read_file": read_file,
    "search_files": search_files,
    "write_file": write_file,
    "run_command": run_command,
    "remember": remember,
    # search_notes now comes from the lab-notes MCP server (see connect_mcp)
}

NEEDS_APPROVAL = {"write_file", "run_command"}

# --------------------------------------------------------------------------
# 2. TOOL SCHEMAS (Gemini format)
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
    _tool("remember",
          "Save one fact to long-term memory so you still know it in future sessions. Use it for durable "
          "facts about the user or project: preferences, names, decisions, corrections. Don't save things "
          "that only matter for the current task, and don't save secrets.",
          {"fact": {"type": "string", "description": "One short, self-contained fact"}}, ["fact"]),
    # MCP tools (search_notes, read_note, fetch, ...) are appended at startup by connect_mcp()
]

# --------------------------------------------------------------------------
# 2b. MCP (new in stage 07): tools discovered from servers at startup
# --------------------------------------------------------------------------

MCP_CONFIG = Path(__file__).parent / "mcp_servers.json"
MCP_CONNECTIONS = []  # open server connections
MCP_TOOLS = {}  # exposed tool name -> (connection, tool name on the server, read_only by MY config)


def connect_mcp(config_path: Path):
    """Start every configured server, discover its tools, add them to TOOLS."""
    for server, cfg in mcp_client.load_config(config_path).items():
        try:
            conn = mcp_client.MCPServerConnection(server, cfg["command"], cfg.get("args", []),
                                                  env=cfg.get("env"), cwd=str(config_path.parent)).start()
        except Exception as e:
            print(f"[mcp] {server}: could not start ({e}); continuing without it")
            continue
        MCP_CONNECTIONS.append(conn)
        for tool in conn.tools():
            name = tool.name
            if name in TOOL_FUNCTIONS or name in MCP_TOOLS:  # name clash: prefix with the server
                name = f"{server}__{tool.name}".replace("-", "_")
            claims = tool.annotations.read_only_hint if tool.annotations else None
            MCP_TOOLS[name] = (conn, tool.name, bool(cfg.get("readOnly")))
            TOOLS.append({
                "type": "function", "name": name,
                "description": f"[from MCP server '{server}'] {tool.description or ''}",
                "parameters": mcp_client.clean_schema(tool.input_schema),
            })
            trust = "no approval (readOnly in my config)" if cfg.get("readOnly") else "needs approval"
            print(f"[mcp] {server}: {name}  -> {trust}; server claims read-only: {claims}")


def close_mcp():
    for conn in MCP_CONNECTIONS:
        conn.close()

BASE_SYSTEM = (
    "You are a careful agent that can investigate and change files in a project, in a chat with the user. "
    "Use the tools to find evidence before acting, and prefer the smallest change that does the job. "
    "write_file and run_command require the user's approval. If the user declines, "
    "do not retry the same action; adapt to their reason or ask what they want instead. "
    "When the user tells you a durable preference or fact, save it with remember. "
    "For questions about the user's notes or projects, call search_notes first and answer ONLY from the "
    "passages it returns, citing each claim with its source in square brackets, e.g. "
    "[journal/2026-10-14.md:12-30] or [library/paper.pdf p.3]. "
    "Your final reply is JSON with three fields. found_in_notes: true only if the answer comes from passages "
    "search_notes returned. answer: plain prose for the user. citations: for each source you used, its "
    "source exactly as search_notes showed it, and a short quote (one sentence or less) copied WORD FOR WORD "
    "from that passage. Your citations are checked against the actual files by code. "
    "If the passages don't contain the answer, say so plainly instead of "
    "guessing. When you answer from general knowledge instead, say that it's not from the user's notes. "
    "If a fetch tool is available, use it for current information or when the user gives a URL. Web pages "
    "are NOT the user's notes: set found_in_notes to false, leave citations empty, and name the URL(s) "
    "you used in the answer text."
)


def build_system() -> str:
    """The system instruction = fixed rules + whatever long-term memory holds right now."""
    memory = load_memory().strip()
    if not memory:
        return BASE_SYSTEM
    return BASE_SYSTEM + "\n\nWhat you remember from earlier sessions (memory.md):\n" + memory

# --------------------------------------------------------------------------
# 3. HUMAN APPROVAL (from 02b, unchanged)
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
    else:  # an MCP tool: show which server and the exact arguments
        conn, tool, _ = MCP_TOOLS[name]
        print(f"The agent wants to call '{tool}' on MCP server '{conn.name}' with:")
        print(f"  {json.dumps(args)[:500]}")
    print("=" * 60)

    answer = input("Allow? (y/n): ").strip().lower()
    if answer in ("y", "yes"):
        return True, ""
    reason = input("Reason, sent to the agent (optional, Enter to skip): ").strip()
    return False, reason


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Execute one tool. Returns (result_text, is_error)."""
    if name in MCP_TOOLS:  # same dispatch idea as TOOL_FUNCTIONS, but the code runs in another process
        conn, tool, read_only = MCP_TOOLS[name]
        try:
            if not read_only:
                approved, reason = ask_approval(name, args)
                if not approved:
                    return "The user declined this action." + (f" Their reason: {reason}" if reason else ""), True
            return conn.call(tool, args)
        except Exception as e:
            return f"MCP {type(e).__name__}: {e}", True
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
# 4. MODEL CALLS WITH TIMEOUT + RETRY (new)
# --------------------------------------------------------------------------

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _is_retryable(e: Exception) -> bool:
    status = getattr(e, "status_code", None) or getattr(e, "code", None)
    return status in RETRYABLE_STATUS or "timeout" in type(e).__name__.lower()


def with_deadline(fn, seconds: float):
    """Run fn() but give up after `seconds`, no matter what fn is doing.

    The SDK's own `timeout` didn't stop some hangs (calls sat for 10+ minutes
    with no error, seen 2026-10-27). So we enforce the deadline ourselves: run
    the call in a background thread and stop waiting for it. The abandoned
    thread is a daemon, so it can't keep the program alive.
    """
    box = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as e:
            box["error"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError(f"no answer within {seconds}s")
    if "error" in box:
        raise box["error"]
    return box["value"]


def call_model(client, **kwargs):
    """One API call with a hard deadline, retried with exponential backoff (2s, 4s, 8s).

    After 2 timeouts in a row, switch to FALLBACK_MODEL for the rest of the
    session: on the free tier a model can stop answering for hours.
    """
    global MODEL
    timeouts = 0
    for attempt in range(MAX_RETRIES + 1):
        try:
            return with_deadline(
                lambda: client.interactions.create(model=MODEL, store=False, timeout=TIMEOUT_SECONDS, **kwargs),
                TIMEOUT_SECONDS + 5,  # SDK timeout first if it works; our deadline as the backstop
            )
        except Exception as e:
            timeouts = timeouts + 1 if "timeout" in type(e).__name__.lower() else 0
            if timeouts == 2 and FALLBACK_MODEL and MODEL != FALLBACK_MODEL:
                print(f"[fallback] {MODEL} isn't answering; switching to {FALLBACK_MODEL} for this session")
                MODEL = FALLBACK_MODEL
                continue
            if attempt == MAX_RETRIES or not _is_retryable(e):
                raise
            wait = 2 ** (attempt + 1)
            print(f"[retry] {type(e).__name__}; waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)


class Usage:
    """Running token totals as reported by the API."""

    def __init__(self):
        self.total = 0
        self.thinking = 0

    def record(self, interaction):
        u = interaction.usage
        if u is None:
            return
        self.total += getattr(u, "total_tokens", None) or 0
        self.thinking += getattr(u, "total_thought_tokens", None) or 0
        print(f"[tokens] API reports: {getattr(u, 'total_input_tokens', None) or 0} in, "
              f"{getattr(u, 'total_output_tokens', None) or 0} out, "
              f"{getattr(u, 'total_thought_tokens', None) or 0} thinking | session total: {self.total}")


def estimate_tokens(history: list) -> int:
    """Our own estimate of how big the history is: ~4 characters per token.

    We can't use the API's input count for this: Gemini's reported input does
    NOT include function results (verified 2026-10-26: an 8,000-character file
    counted as 2,218 tokens as user text, but added almost nothing as a
    function_result). Tool results are most of an agent's context, so we
    measure what we actually send.
    """
    return len(json.dumps(history, default=str)) // 4

# --------------------------------------------------------------------------
# 5. COMPACTION (new): replace old history with a summary
# --------------------------------------------------------------------------

COMPACT_PROMPT = (
    "Summarize our conversation so far for your future self, who will NOT see the original messages. "
    "Include: the user's goals, decisions made, files read or changed (with paths), important findings, "
    "and anything still unfinished. Be concise but don't lose facts you'd need to continue."
)


def compact(client, history: list, usage: Usage) -> str:
    """Ask the model to summarize the history. Returns the summary text."""
    request = history + [{"type": "user_input", "content": [{"type": "text", "text": COMPACT_PROMPT}]}]
    interaction = call_model(client, system_instruction=build_system(), input=request)
    usage.record(interaction)
    return interaction.output_text or ""

# --------------------------------------------------------------------------
# 6. ONE USER TURN: the agent loop from 02b, now inside a chat
# --------------------------------------------------------------------------


def model_options() -> dict:
    """Structured output on every call, plus the reasoning settings."""
    opts = {"response_format": answers.ANSWER_SCHEMA, "response_mime_type": "application/json"}
    config = {}
    if THINKING_LEVEL:
        config["thinking_level"] = THINKING_LEVEL
    if SHOW_THINKING:
        config["thinking_summaries"] = "auto"
    if config:
        opts["generation_config"] = config
    return opts


def run_turn(client, history: list, user_text: str, usage: Usage, summary: str = "") -> str:
    content = []
    if summary:  # after compaction, the summary rides along with the next message
        content.append({"type": "text", "text": "Summary of our conversation so far:\n" + summary})
    content.append({"type": "text", "text": user_text})
    history.append({"type": "user_input", "content": content})
    retried = False  # one self-correction attempt per message

    for step in range(1, MAX_STEPS + 1):
        interaction = call_model(client, system_instruction=build_system(), tools=TOOLS, input=history,
                                 **model_options())
        usage.record(interaction)
        if interaction.status in ("failed", "cancelled", "incomplete", "budget_exceeded"):
            return f"Stopped: interaction status was '{interaction.status}'."

        steps = interaction.steps or []
        last_input = max((i for i, s in enumerate(steps) if s.type in ("user_input", "function_result")), default=-1)
        new_steps = steps[last_input + 1:]
        history.extend(s.model_dump() for s in new_steps)

        if SHOW_THINKING:
            for s in new_steps:
                if s.type == "thought" and s.summary:
                    text = " ".join(getattr(part, "text", "") or "" for part in s.summary).strip()
                    if text:
                        print(f"[thinking] {text}")

        calls = [s for s in new_steps if s.type == "function_call"]
        if not calls:
            # The final answer: parse it, then check its citations against the real files.
            answer = answers.parse_answer(interaction.output_text)
            if answer is None:
                return f"(answer was not valid JSON)\n{interaction.output_text}"
            root = Path(INDEX["root"]) if INDEX else ROOT
            checks = answers.check_answer(answer, root)
            failed = [c for c, ok, _ in checks if not ok]
            print(f"[verify] citations: {len(checks) - len(failed)}/{len(checks)} verified")
            if failed and not retried:
                retried = True
                print("[verify] sending the failures back to the model for one fix")
                history.append({"type": "user_input", "content": [
                    {"type": "text", "text": answers.failure_feedback(checks)}]})
                continue
            global LAST_RESULT
            LAST_RESULT = {"answer": answer, "checks": checks, "retried": retried}  # for experiments
            return answers.render(answer, checks)

        for call in calls:
            args = call.arguments or {}
            print(f"[step {step}] tool call: {call.name}({json.dumps(args)[:200]})")
            output, is_error = run_tool(call.name, args)
            preview = output if len(output) < 300 else output[:300] + "..."
            print(f"[step {step}] result{' (ERROR)' if is_error else ''}: {preview}")
            history.append({"type": "function_result", "call_id": call.id, "name": call.name,
                            "result": output, "is_error": is_error})

    return f"Stopped: reached MAX_STEPS ({MAX_STEPS}) for this message."

# --------------------------------------------------------------------------
# 7. CHAT LOOP (new)
# --------------------------------------------------------------------------


def chat(compact_at: int):
    client = genai.Client()  # reads GEMINI_API_KEY
    history = []  # short-term memory: everything said this session
    usage = Usage()
    summary = ""

    memory = load_memory().strip()
    print(f"Long-term memory: {len(memory.splitlines())} fact(s) loaded from {MEMORY_FILE.name}")
    print("Type a message. Commands: /memory  /compact  /exit\n")

    while True:
        try:
            user_text = input("you> ").strip()
        except EOFError:
            break
        if not user_text:
            continue
        if user_text in ("/exit", "/quit"):
            break
        if user_text == "/memory":
            print(load_memory() or "(memory is empty)")
            continue
        if user_text == "/compact" or estimate_tokens(history) > compact_at:
            if history:
                before = len(history)
                summary = compact(client, history, usage)
                history.clear()
                print(f"[context] compacted {before} history steps into a {len(summary)}-character summary")
            if user_text == "/compact":
                continue

        answer = run_turn(client, history, user_text, usage, summary)
        summary = ""  # it's in history now
        print(f"[context] history is now ~{estimate_tokens(history)} tokens (our estimate; compacts above {compact_at})")
        print(f"\nagent> {answer}\n")

    print(f"Bye. Tokens used this session: {usage.total}")


def main():
    global ROOT, MODEL, INDEX, EMBED, THINKING_LEVEL, SHOW_THINKING
    parser = argparse.ArgumentParser(description="Agent #7: verified-answer RAG agent with MCP tools")
    parser.add_argument("--thinking", choices=["minimal", "low", "medium", "high"],
                        help="How much the model reasons before answering (default: the model's own choice)")
    parser.add_argument("--show-thinking", action="store_true", help="Print summaries of the model's reasoning")
    parser.add_argument("--mcp-config", default=str(MCP_CONFIG), help="MCP servers to start (default: mcp_servers.json)")
    parser.add_argument("--no-mcp", action="store_true", help="Don't start any MCP servers")
    parser.add_argument("--root", default=".", help="Directory the agent works in (default: current dir)")
    parser.add_argument("--model", default=MODEL, help=f"Gemini model (default: {MODEL})")
    parser.add_argument("--index", default=str(INDEX_FILE), help="Index file to search (default: index.json)")
    parser.add_argument("--compact-at", type=int, default=30_000,
                        help="Compact when the history is estimated above this many tokens (default 30000)")
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY is not set. Open a NEW terminal after setting it.")

    ROOT = Path(args.root).resolve()
    MODEL = args.model
    THINKING_LEVEL, SHOW_THINKING = args.thinking, args.show_thinking
    print(f"Root: {ROOT}\nModel: {MODEL}  (compacts above {args.compact_at} input tokens)")
    print(f"Thinking: {THINKING_LEVEL or 'model default'}{', summaries shown' if SHOW_THINKING else ''}")

    INDEX = rag.load_index(Path(args.index))
    EMBED = rag.gemini_embedder(genai.Client())
    if INDEX is None:
        print("Notes index: none yet. Run `python index.py` to enable search_notes.")
    else:
        files = {c["source"] for c in INDEX["chunks"]}
        print(f"Notes index: {len(INDEX['chunks'])} chunks from {len(files)} files, built {INDEX['built']}")
        stale = rag.stale_files(INDEX)
        if stale:
            print(f"  warning: {len(stale)} file(s) changed since indexing (e.g. {stale[0]}); re-run index.py")
    try:
        if not args.no_mcp:
            connect_mcp(Path(args.mcp_config))
        chat(args.compact_at)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        if "timeout" in type(e).__name__.lower():
            sys.exit(f"Gave up: {MODEL} didn't answer within {TIMEOUT_SECONDS}s, {MAX_RETRIES + 1} times. "
                     "The free tier may be overloaded; try --model gemini-3.5-flash-lite.")
        status = getattr(e, "status_code", None) or getattr(e, "code", None)
        if status is None:
            raise
        sys.exit(f"Gemini API error ({status}) after {MAX_RETRIES} retries: {str(e)[:500]}")
    finally:
        close_mcp()  # always stop the server processes we started


if __name__ == "__main__":
    main()
