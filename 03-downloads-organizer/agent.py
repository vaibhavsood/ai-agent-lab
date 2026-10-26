"""
Agent #3: a Downloads organizer that plans first, then acts.

The model LOOKS (scan_folder), then PLANS (propose_plan). You review the whole
plan once. If you approve, this code (not the model) validates and executes
the moves and writes an undo log. If you reject, your feedback goes back to
the model and it revises the plan.

    python make_fake_downloads.py                          # practice folder
    python agent.py --root ../../sandbox/fake-downloads    # organize it
    python agent.py --root ../../sandbox/fake-downloads --undo   # put it all back

Runs on Gemini's free tier. Free-tier data may be used by Google, so practice
on the fake folder. File NAMES are sent to the model, never file contents.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from google import genai

MODEL = "gemini-3.8-flash"  # free tier
MAX_STEPS = 10
UNDO_LOG = ".organizer-undo.json"

ROOT = Path(".").resolve()

# --------------------------------------------------------------------------
# 1. LOOK: scan_folder. Code does the exact work (sizes, dates, duplicates)
#    so the model can spend its effort on judgment (what goes where).
# --------------------------------------------------------------------------


def _top_level_files() -> list[Path]:
    return sorted(p for p in ROOT.iterdir() if p.is_file() and not p.name.startswith("."))


def scan_folder() -> str:
    files = _top_level_files()
    seen = {}  # content hash -> first file with that content
    rows = []
    # Shortest name first, so "a.pdf" is the original and "a (1).pdf" the duplicate.
    for p in sorted(files, key=lambda p: (len(p.name), p.name)):
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        rows.append({
            "name": p.name,
            "extension": p.suffix.lower() or "(none)",
            "size_bytes": p.stat().st_size,
            "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d"),
            "duplicate_of": seen.get(digest),  # identical content to this file, or None
        })
        seen.setdefault(digest, p.name)
    folders = sorted(p.name for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith("."))
    return json.dumps({"existing_folders": folders, "files": sorted(rows, key=lambda r: r["name"])}, indent=1)


# --------------------------------------------------------------------------
# 2. PLAN: propose_plan. The plan arrives as structured data, so code can
#    check it before a human ever sees it.
# --------------------------------------------------------------------------


def validate_plan(moves: list[dict]) -> list[str]:
    """Return a list of problems. Empty list = the plan is safe to show."""
    problems, sources, destinations = [], set(), set()
    for i, m in enumerate(moves, 1):
        name, folder = m.get("file", ""), m.get("folder", "").strip("/\\")
        src = ROOT / name
        if Path(name).name != name or not src.is_file():
            problems.append(f"move {i}: '{name}' is not a file in the top level of the folder")
            continue
        if not folder or ".." in Path(folder).parts or Path(folder).is_absolute():
            problems.append(f"move {i}: folder '{folder}' must be a simple subfolder name")
            continue
        dest = (ROOT / folder / name).resolve()
        if ROOT not in dest.parents:
            problems.append(f"move {i}: '{folder}' is outside the folder")
        elif dest.exists() or dest in destinations:
            problems.append(f"move {i}: '{folder}/{name}' already exists or is used twice")
        elif name in sources:
            problems.append(f"move {i}: '{name}' is moved more than once")
        sources.add(name)
        destinations.add(dest)
    return problems


def show_plan(moves: list[dict], summary: str) -> None:
    by_folder = {}
    for m in moves:
        by_folder.setdefault(m["folder"], []).append(m)
    print("\n" + "=" * 70)
    print(f"PROPOSED PLAN: {summary}")
    print(f"{len(moves)} files into {len(by_folder)} folders. Nothing is deleted.")
    for folder in sorted(by_folder):
        print(f"\n  {folder}/  ({len(by_folder[folder])})")
        for m in by_folder[folder]:
            print(f"    {m['file']:<40} {m.get('reason', '')[:28]}")
    untouched = len(_top_level_files()) - len(moves)
    if untouched:
        print(f"\n  (left where it is: {untouched} file(s))")
    print("=" * 70)


def execute_plan(moves: list[dict]) -> str:
    """Do the moves and append them to the undo log."""
    done, created = [], []
    for m in moves:
        folder = ROOT / m["folder"].strip("/\\")
        missing, d = [], folder  # log every new level, e.g. Images AND Images/Screenshots
        while d != ROOT and not d.exists():
            missing.append(d)
            d = d.parent
        folder.mkdir(parents=True, exist_ok=True)
        created.extend(str(x.relative_to(ROOT)) for x in reversed(missing))
        shutil.move(str(ROOT / m["file"]), str(folder / m["file"]))
        done.append({"from": m["file"], "to": str(Path(m["folder"].strip("/\\")) / m["file"])})

    log_path = ROOT / UNDO_LOG
    batches = json.loads(log_path.read_text()) if log_path.exists() else []
    batches.append({"time": datetime.now().isoformat(timespec="seconds"), "moves": done, "created_folders": created})
    log_path.write_text(json.dumps(batches, indent=1))
    return f"Moved {len(done)} files. Created folders: {', '.join(created) or 'none'}. Undo is available."


def propose_plan(moves: list[dict], summary: str) -> tuple[str, bool]:
    problems = validate_plan(moves)
    if problems:  # don't bother the human with an invalid plan
        return "Plan rejected by validation, fix and propose again:\n" + "\n".join(problems), True

    show_plan(moves, summary)
    if input("Approve this plan? (y/n): ").strip().lower() in ("y", "yes"):
        return execute_plan(moves), False
    feedback = input("What should change? (sent to the agent): ").strip()
    return f"The user rejected the plan. Their feedback: {feedback or '(none given)'}", True


# --------------------------------------------------------------------------
# 3. UNDO: plain code, no model involved.
# --------------------------------------------------------------------------


def undo_last() -> str:
    log_path = ROOT / UNDO_LOG
    batches = json.loads(log_path.read_text()) if log_path.exists() else []
    if not batches:
        return "Nothing to undo."
    batch = batches.pop()
    for m in reversed(batch["moves"]):
        shutil.move(str(ROOT / m["to"]), str(ROOT / m["from"]))
    for folder in reversed(batch["created_folders"]):
        try:
            (ROOT / folder).rmdir()  # only removes it if it's empty
        except OSError:
            pass
    if batches:
        log_path.write_text(json.dumps(batches, indent=1))
    else:
        log_path.unlink()
    return f"Undid {len(batch['moves'])} moves from {batch['time']}."


# --------------------------------------------------------------------------
# 4. TOOL SCHEMAS (Gemini format, as in 02b)
# --------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "name": "scan_folder",
        "description": (
            "List the files in the top level of the folder with extension, size, modified date, "
            "and duplicate_of (set when the file has exactly the same content as another file). "
            "Also lists existing subfolders. Call this first."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "propose_plan",
        "description": (
            "Propose ONE complete plan of file moves. The user reviews the whole plan at once. "
            "If approved, the moves are executed and you get a confirmation. If rejected, you get "
            "the user's feedback: revise and propose again. Files can only be moved into subfolders; "
            "nothing can be deleted."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "One sentence describing the organization scheme"},
                "moves": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string", "description": "Exact file name from scan_folder"},
                            "folder": {"type": "string", "description": "Destination subfolder name, e.g. 'Finance'"},
                            "reason": {"type": "string", "description": "A few words on why"},
                        },
                        "required": ["file", "folder", "reason"],
                    },
                },
            },
            "required": ["summary", "moves"],
        },
    },
]

SYSTEM = (
    "You organize a messy downloads folder. First call scan_folder. Then call propose_plan once "
    "with a complete plan covering every file. Use a small number of clear, human folder names "
    "(for example Documents, Finance, Images, Screenshots, Installers, Archives, Media). "
    "Put every file whose duplicate_of is set into a folder named _Duplicates so the user can "
    "review them; never try to delete anything. If the user rejects the plan, follow their "
    "feedback exactly and propose a revised complete plan. After a plan is executed, reply with a "
    "short summary and stop."
)

# --------------------------------------------------------------------------
# 5. THE AGENT LOOP (same as 02b)
# --------------------------------------------------------------------------


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    try:
        if name == "scan_folder":
            return scan_folder(), False
        if name == "propose_plan":
            return propose_plan(args.get("moves", []), args.get("summary", ""))
        return f"Unknown tool: {name}", True
    except Exception as e:  # errors go back to the model so it can recover
        return f"{type(e).__name__}: {e}", True


def run_agent(task: str) -> str:
    client = genai.Client()  # reads GEMINI_API_KEY
    history = [{"type": "user_input", "content": [{"type": "text", "text": task}]}]

    for step in range(1, MAX_STEPS + 1):
        interaction = client.interactions.create(
            model=MODEL, system_instruction=SYSTEM, tools=TOOLS, input=history, store=False,
        )
        if interaction.status in ("failed", "cancelled", "incomplete", "budget_exceeded"):
            return f"Stopped: interaction status was '{interaction.status}'."

        steps = interaction.steps or []
        last_input = max((i for i, s in enumerate(steps) if s.type in ("user_input", "function_result")), default=-1)
        new_steps = steps[last_input + 1:]
        history.extend(s.model_dump() for s in new_steps)

        calls = [s for s in new_steps if s.type == "function_call"]
        if not calls:
            return interaction.output_text or "(the model returned no text)"

        for call in calls:
            args = call.arguments or {}
            label = f"{len(args.get('moves', []))} moves" if call.name == "propose_plan" else ""
            print(f"[step {step}] tool call: {call.name}({label})")
            output, is_error = run_tool(call.name, args)
            preview = output if len(output) < 200 else output[:200] + "..."
            print(f"[step {step}] result{' (ERROR)' if is_error else ''}: {preview}")
            history.append({"type": "function_result", "call_id": call.id, "name": call.name,
                            "result": output, "is_error": is_error})

    return f"Stopped: reached MAX_STEPS ({MAX_STEPS}) without a final answer."


def main():
    global ROOT
    parser = argparse.ArgumentParser(description="Agent #3: plan-then-execute Downloads organizer")
    parser.add_argument("--root", required=True, help="The folder to organize")
    parser.add_argument("--undo", action="store_true", help="Undo the last executed plan (no model needed)")
    parser.add_argument("--task", default="Organize this downloads folder.", help="Extra instructions for the agent")
    args = parser.parse_args()

    ROOT = Path(args.root).resolve()
    if not ROOT.is_dir():
        sys.exit(f"Not a folder: {ROOT}")
    if args.undo:
        print(undo_last())
        return
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY is not set. Open a NEW terminal after setting it.")

    print(f"Organizing: {ROOT}\nModel: {MODEL}")
    try:
        answer = run_agent(args.task)
    except KeyboardInterrupt:
        sys.exit("\nStopped by user.")
    except Exception as e:
        status = getattr(e, "status_code", None) or getattr(e, "code", None)
        if status is None:
            raise
        if status == 429:
            sys.exit("Free-tier rate limit reached. Wait a minute and retry.")
        sys.exit(f"Gemini API error ({status}): {str(e)[:500]}")
    print("\n=== AGENT SAYS ===\n" + answer)


if __name__ == "__main__":
    main()
