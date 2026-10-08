"""
Offline tests for the approval gate. No API key needed.

We can't type y/n into a test, so we replace Python's input() with a fake
that returns scripted answers ("mocking" the human).

    python test_approval.py
"""

import builtins
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agent

sandbox = Path(tempfile.mkdtemp(prefix="stage02-"))
agent.ROOT = sandbox


def answers(*replies):
    """Fake the human: each input() call returns the next reply."""
    it = iter(replies)

    def fake_input(prompt=""):
        reply = next(it)
        print(f"{prompt}{reply}   <- (fake human)")
        return reply

    builtins.input = fake_input


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {label}\n")
    if not cond:
        sys.exit(1)


# 1. Approved write creates the file
answers("y")
out, err = agent.run_tool("write_file", {"path": "hello.py", "content": "print('hi')\n"})
check("approved write_file creates the file", not err and (sandbox / "hello.py").read_text() == "print('hi')\n")

# 2. Declined write with a reason: file untouched, reason reaches the model
answers("n", "call it greet.py instead")
out, err = agent.run_tool("write_file", {"path": "hello.py", "content": "OVERWRITTEN"})
print("tool_result sent to model:", out)
check("declined write keeps the file and returns the reason", err and "greet.py" in out and (sandbox / "hello.py").read_text() == "print('hi')\n")

# 3. Writing outside the sandbox fails before the human is even asked
answers()  # no replies: input() must not be called
out, err = agent.run_tool("write_file", {"path": "../escape.txt", "content": "x"})
print("tool_result sent to model:", out)
check("write outside root is refused without asking", err and "outside the allowed root" in out)

# 4. Approved command runs and returns exit code + output
answers("y")
out, err = agent.run_tool("run_command", {"command": f'"{sys.executable}" hello.py'})
print("tool_result sent to model:", out)
check("approved run_command runs in the sandbox", not err and "exit code: 0" in out and "hi" in out)

# 5. Declined command with no reason
answers("n", "")
out, err = agent.run_tool("run_command", {"command": "del hello.py" if sys.platform == "win32" else "rm hello.py"})
print("tool_result sent to model:", out)
check("declined run_command does not run", err and out == "The user declined this action." and (sandbox / "hello.py").exists())

# 6. Read-only tools never ask
answers()
out, err = agent.run_tool("read_file", {"path": "hello.py"})
check("read_file runs without approval", not err and "print('hi')" in out)

print("All stage 02 checks passed.")
