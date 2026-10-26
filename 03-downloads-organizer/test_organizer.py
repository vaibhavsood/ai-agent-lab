"""
Offline tests for the organizer's code paths. No API key needed.

    python test_organizer.py
"""

import builtins
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import agent

folder = Path(tempfile.mkdtemp(prefix="stage03-")) / "downloads"
subprocess.run([sys.executable, str(HERE / "make_fake_downloads.py"), str(folder)], check=True)
agent.ROOT = folder
before = sorted(p.name for p in folder.iterdir())


def answers(*replies):
    it = iter(replies)
    builtins.input = lambda prompt="": print(f"{prompt}{(r := next(it))}   <- (fake human)") or r


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    if not cond:
        sys.exit(1)


# 1. scan_folder finds exactly the 3 duplicates, and marks the "(1)" copies
scan = json.loads(agent.scan_folder())
dups = {f["name"]: f["duplicate_of"] for f in scan["files"] if f["duplicate_of"]}
check("scan finds the 3 duplicates", dups == {
    "invoice_2026_04_acme (1).pdf": "invoice_2026_04_acme.pdf",
    "Resume_final_v3 (1).docx": "Resume_final_v3.docx",
    "IMG_20260912_101544 (1).jpg": "IMG_20260912_101544.jpg",
})

# 2. validation catches every unsafe plan before the human is asked
answers()  # input() must not be called
bad = [
    {"file": "todo.txt", "folder": "../outside", "reason": ""},
    {"file": "does_not_exist.pdf", "folder": "Docs", "reason": ""},
    {"file": "meeting_notes.txt", "folder": "Docs", "reason": ""},
    {"file": "meeting_notes.txt", "folder": "Other", "reason": ""},
]
out, err = agent.propose_plan(bad, "bad plan")
print("   ->", out.replace("\n", "\n      "))
check("invalid plan is rejected without asking", err and "outside" in out and "not a file" in out and "more than once" in out)

# 3. a rejected plan moves nothing and returns the feedback
plan = [{"file": "todo.txt", "folder": "Documents", "reason": "notes"},
        {"file": "song_demo.mp3", "folder": "Media", "reason": "audio"}]
answers("n", "put audio in Music")
out, err = agent.propose_plan(plan, "test plan")
check("rejected plan returns feedback and moves nothing", err and "Music" in out and sorted(p.name for p in folder.iterdir()) == before)

# 4. an approved plan is executed and logged (including a nested folder)
plan.append({"file": "Screenshot 2026-10-01 093012.png", "folder": "Images/Screenshots", "reason": "screenshot"})
answers("y")
out, err = agent.propose_plan(plan, "test plan")
check("approved plan moves the files", not err and (folder / "Documents" / "todo.txt").exists()
      and (folder / "Images" / "Screenshots" / "Screenshot 2026-10-01 093012.png").exists())
check("undo log written", (folder / agent.UNDO_LOG).exists())

# 5. undo restores the folder exactly
print("   ->", agent.undo_last())
check("undo restores every file and removes the new folders", sorted(p.name for p in folder.iterdir()) == before)

print("\nAll stage 03 checks passed.")
