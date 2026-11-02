"""
Offline tests for stage 06: schema parsing, citation checking, self-correction.
No API key needed: the model is mocked.

    python test_structured.py
"""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parent / "05-rag"))  # LAST, only for make_sample_pdf: 05-rag has its own agent.py!
import agent
import answers
from make_sample_pdf import make_pdf


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    if not cond:
        sys.exit(1)


# A small "notes folder" to cite from
root = Path(tempfile.mkdtemp())
(root / "notes.md").write_text("# Loop\n\nThe agent stops after MAX_STEPS so it cannot run forever.\n"
                               + "filler line\n" * 20 + "## Memory\nLong-term memory is a file called memory.md.\n")
make_pdf(root / "paper.pdf", ["Intro page", "ReAct alternates Thought, Action and Observation."])

# 1. parsing: valid JSON in the right shape passes; anything else is rejected
good = {"found_in_notes": True, "answer": "x", "citations": []}
check("valid answer JSON is parsed", answers.parse_answer(json.dumps(good)) == good)
check("text that isn't JSON is rejected", answers.parse_answer("The answer is 4.") is None)
check("JSON with a missing field is rejected", answers.parse_answer('{"answer": "x"}') is None)

# 2. citation checks against the real files
ok = lambda src, q: answers.check_citation({"source": src, "quote": q}, root)
check("exact quote at the cited lines passes", ok("notes.md:1-3", "The agent stops after MAX_STEPS")[0])
check("case, line breaks and markdown don't matter", ok("[notes.md:1-3]", "the agent STOPS after `MAX_STEPS`")[0])
check("a quote with '...' between real parts passes", ok("notes.md:1-3", "The agent stops ... cannot run forever")[0])
check("a paraphrase fails", ok("notes.md:1-3", "The agent halts once it reaches the step limit")
      == (False, "quote not found at that location"))
check("a real quote 3 lines past the cited range passes (slack)", ok("notes.md:20-22", "Long-term memory is a file")[0])
check("a real quote at the WRONG lines fails", not ok("notes.md:1-3", "Long-term memory is a file")[0])
check("a PDF quote on the right page passes", ok("paper.pdf p.2", "ReAct alternates Thought, Action")[0])
check("a PDF quote on the wrong page fails", not ok("paper.pdf p.1", "ReAct alternates Thought, Action")[0])
check("a citation of a file that doesn't exist fails", ok("made_up.md:1-5", "something long enough") == (False, "no such file: made_up.md"))
check("a too-short quote can't be verified", ok("notes.md:1-3", "agent") == (False, "quote too short to verify"))

# 3. the full loop: a made-up quote is caught, fed back, and fixed
def final(answer):
    return NS(steps=[NS(type="model_output", content=[], model_dump=lambda: {"type": "model_output"})],
              output_text=json.dumps(answer), status="completed", usage=None)


class FakeClient:
    def __init__(self, replies):
        self.replies, self.requests, self.interactions = list(replies), [], self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.replies.pop(0)


bad_answer = {"found_in_notes": True, "answer": "It stops at a limit.",
              "citations": [{"source": "notes.md:1-3", "quote": "The agent halts at the step limit"}]}
fixed_answer = {"found_in_notes": True, "answer": "It stops at a limit.",
                "citations": [{"source": "notes.md:1-3", "quote": "The agent stops after MAX_STEPS"}]}
agent.INDEX = {"root": str(root), "chunks": []}
client = FakeClient([final(bad_answer), final(fixed_answer)])
history = []
out = agent.run_turn(client, history, "How does it avoid running forever?", agent.Usage())
check("every call asks for the answer schema", all(r.get("response_format") == answers.ANSWER_SCHEMA for r in client.requests))
check("the failed citation was sent back to the model", any("failed" in json.dumps(h) for h in history if h["type"] == "user_input"))
check("after the fix, the answer shows 1/1 verified", "1/1 verified" in out and "✓" in out)

# 4. a second failure is shown honestly instead of retried forever
client = FakeClient([final(bad_answer), final(bad_answer)])
out = agent.run_turn(client, [], "Again?", agent.Usage())
check("only ONE fix attempt; then the answer is shown with ✗", len(client.requests) == 2 and "0/1 verified" in out and "✗" in out)

# 5. reasoning settings reach the API
agent.THINKING_LEVEL, agent.SHOW_THINKING = "high", True
check("--thinking and --show-thinking become generation_config",
      agent.model_options()["generation_config"] == {"thinking_level": "high", "thinking_summaries": "auto"})

print("\nAll stage 06 checks passed.")
