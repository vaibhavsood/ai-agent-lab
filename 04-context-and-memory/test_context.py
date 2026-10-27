"""
Offline tests for stage 04. No API key needed: the MODEL is mocked too.

A fake client returns scripted replies (a tool call, then text), so we can
test the loop, memory, retries and compaction deterministically and for free.

    python test_context.py
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).parent))
import agent

agent.MEMORY_FILE = Path(tempfile.mkdtemp()) / "memory.md"
agent.time.sleep = lambda s: None  # don't actually wait during retry tests


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    if not cond:
        sys.exit(1)


# ---- fake model pieces -----------------------------------------------------

def step(type_, **fields):
    s = NS(type=type_, **fields)
    s.model_dump = lambda: {"type": type_, **{k: v for k, v in fields.items()}}
    return s


def reply(steps, text="", input_tokens=100):
    return NS(steps=steps, output_text=text, status="completed",
              usage=NS(total_input_tokens=input_tokens, total_output_tokens=10, total_tokens=input_tokens + 10))


class FakeClient:
    """Plays back scripted replies; records every request it receives."""

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []
        self.interactions = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeTimeout(Exception):
    pass


class FakeHTTPError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status_code = status


# 1. remember() writes to memory.md, and the next system instruction includes it
agent.remember("The user's test codeword is blue-falcon")
check("remember appends a fact to memory.md", "blue-falcon" in agent.MEMORY_FILE.read_text())
check("system instruction includes long-term memory", "blue-falcon" in agent.build_system())

# 2. the loop inside run_turn: tool call -> result -> final text
agent.ROOT = Path(__file__).parent
client = FakeClient([
    reply([step("model_output", content=[]), step("function_call", id="c1", name="list_files", arguments={})]),
    reply([step("model_output", content=[])], text="There are 4 files."),
])
usage = agent.Usage()
history = []
answer = agent.run_turn(client, history, "How many files?", usage)
types = [h["type"] for h in history]
check("run_turn runs the tool and returns the final text", answer == "There are 4 files.")
check("history is user_input -> model steps -> function_result -> model steps",
      types == ["user_input", "model_output", "function_call", "function_result", "model_output"])
check("every call had a timeout", all(r.get("timeout") == agent.TIMEOUT_SECONDS for r in client.requests))

# 3. retries: two timeouts then success; a 400 is not retried
client = FakeClient([FakeTimeout(), FakeHTTPError(503), reply([], text="ok")])
check("timeout and 503 are retried, then the call succeeds", agent.call_model(client, input=[]).output_text == "ok")
client = FakeClient([FakeHTTPError(400), reply([], text="never")])
try:
    agent.call_model(client, input=[])
    check("400 is not retried", False)
except FakeHTTPError:
    check("400 is not retried", len(client.requests) == 1)

# 4. compaction: summary replaces history and rides along with the next message
client = FakeClient([reply([], text="User asked about files; there are 4.")])
summary = agent.compact(client, history, usage)
check("compact asks the model for a summary of the full history",
      client.requests[0]["input"][:-1] == history and summary.startswith("User asked"))
history.clear()
client = FakeClient([reply([step("model_output", content=[])], text="Still 4.")])
agent.run_turn(client, history, "And now?", usage, summary)
first = history[0]["content"]
check("after compaction, the next message carries the summary", len(history) == 2 and "User asked" in first[0]["text"] and first[1]["text"] == "And now?")

# 5. the size estimate counts tool results (the API's own count doesn't)
big = [{"type": "function_result", "call_id": "x", "name": "read_file", "result": "x" * 8000}]
check("estimate_tokens counts an 8,000-char tool result as ~2,000 tokens", 1900 < agent.estimate_tokens(big) < 2200)

print("\nAll stage 04 checks passed.")
