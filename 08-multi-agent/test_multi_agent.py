"""
Offline tests for the team: a FAKE model client, no API key, no MCP servers.

    python test_multi_agent.py

The fake recognizes which agent is calling by its system instruction, and
records every request, so we can check what each agent actually SAW.
"""

import json
import threading
import time

import agent

PASSED = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}{'  -- ' + detail if detail and not condition else ''}")
    PASSED.append(bool(condition))


# ---------- a fake Interactions API ----------------------------------------


class Step:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def model_dump(self):
        return dict(self.__dict__)


class Interaction:
    def __init__(self, steps, text=""):
        self.status = "completed"
        self.steps = steps
        self.output_text = text
        self.usage = Step(total_tokens=100)


def call(name, task, cid):
    return Step(type="function_call", name=name, arguments={"task": task}, id=cid)


def final(text):
    return Interaction([Step(type="model_output", text=text)], text)


class FakeClient:
    def __init__(self, script):
        self.script = script  # fn(who, request) -> Interaction
        self.requests = []
        self.lock = threading.Lock()
        self.interactions = self

    def create(self, **kw):
        system = kw["system_instruction"]
        who = ("lead" if system.startswith("You lead") else
               "notes" if "personal notes" in system else
               "reviewer" if system.startswith("You review") else "other")
        with self.lock:  # snapshot: the agent keeps appending to the same history list later
            self.requests.append((who, json.loads(json.dumps(kw, default=str))))
        return self.script(who, kw)


def has_results(kw):
    return any(s.get("type") == "function_result" for s in kw["input"])


def setup(script):
    agent.CLIENT = FakeClient(script)
    agent.TOOLS["search_notes"] = {"schema": {"type": "function", "name": "search_notes"},
                                   "fn": lambda a: ("[notes.md:1-2] passage", False)}
    agent.TOOLS["read_note"] = {"schema": {"type": "function", "name": "read_note"},
                                "fn": lambda a: ("text", False)}
    agent.USAGE.rows = {}
    return agent.CLIENT


ANSWER = json.dumps({"found_in_notes": False, "answer": "done", "citations": []})


# ---------- 1. context isolation -------------------------------------------

def script_isolation(who, kw):
    if who == "lead":
        if not has_results(kw):
            return Interaction([call("ask_notes_researcher", "Find what the notes say about MCP.", "c1")])
        return final(ANSWER)
    return final("- MCP is a protocol [notes.md:1-2] \"MCP is a protocol\"")


client = setup(script_isolation)
history = [{"type": "user_input", "content": [{"type": "text", "text": "SECRET earlier chat message"}]}]
agent.LEAD.run("What do my notes say about MCP?", history)
worker_inputs = [kw["input"] for who, kw in client.requests if who == "notes"]
check("researcher was called", len(worker_inputs) == 1)
first = worker_inputs[0]
check("researcher's history starts with ONLY the task", len(first) == 1 and
      first[0]["content"][0]["text"] == "Find what the notes say about MCP.", json.dumps(first)[:200])
check("researcher never saw the lead's chat", "SECRET" not in json.dumps(worker_inputs))
results = [s for s in history if s.get("type") == "function_result"]
check("only the REPORT went back into the lead's history",
      len(results) == 1 and results[0]["result"].startswith("- MCP is a protocol"))


# ---------- 2. parallel fan-out --------------------------------------------

def script_parallel(who, kw):
    if who == "lead":
        if not has_results(kw):
            return Interaction([call("ask_notes_researcher", "Task A", "a"),
                                call("ask_notes_researcher", "Task B", "b")])
        return final(ANSWER)
    time.sleep(1.0)  # each researcher "thinks" for 1 second
    return final("report for " + kw["input"][0]["content"][0]["text"])


setup(script_parallel)
history = []
start = time.time()
agent.LEAD.run("two things", history)
elapsed = time.time() - start
check("two 1-second researchers took ~1s, not 2s (parallel)", elapsed < 1.7, f"{elapsed:.2f}s")
results = [s for s in history if s.get("type") == "function_result"]
check("results keep the order of the calls",
      [r["call_id"] for r in results] == ["a", "b"] and results[0]["result"] == "report for Task A")
row = agent.USAGE.rows.get("notes_researcher", {})
check("usage counted per agent (2 researcher runs)", row.get("runs") == 2 and row.get("calls") == 2, str(row))


# ---------- 3. least privilege ----------------------------------------------

out, is_error = agent.NOTES_RESEARCHER.dispatch("remember", {"fact": "x"})
check("researcher can't use the lead's tools (code refuses)", is_error and "not available" in out)
out, is_error = agent.LEAD.dispatch("search_notes", {"query": "x"})
check("lead can't search itself (it must delegate)", is_error and "not available" in out)


# ---------- 4. reviewer rejects -> one revision ------------------------------

def script_review(who, kw):
    if who == "lead":
        texts = json.dumps(kw["input"])
        if "A reviewer compared" in texts:
            return final(json.dumps({"found_in_notes": False, "answer": "revised", "citations": []}))
        if not has_results(kw):
            return Interaction([call("ask_notes_researcher", "Task", "r1")])
        return final(json.dumps({"found_in_notes": False, "answer": "draft", "citations": []}))
    if who == "reviewer":
        return final(json.dumps({"approved": False, "problems": ["The draft ignores the report."]}))
    return final("report")


client = setup(script_review)
reply = agent.answer_question("question", [], use_reviewer=True)
review_req = [kw for who, kw in client.requests if who == "reviewer"]
check("reviewer got the question, the reports and the draft",
      len(review_req) == 1 and all(s in json.dumps(review_req[0]["input"]) for s in ("question", "report", "draft")))
check("rejected draft was revised by the lead", "revised" in reply, reply)
check("reviewer has no tools", "tools" not in review_req[0])

# ---------- 5. step budget: the last step asks for the report ---------------

def script_endless(who, kw):  # a researcher that would search forever
    if "budget is used up" in json.dumps(kw["input"]):
        return final("report from what I found")
    return Interaction([Step(type="function_call", name="search_notes", arguments={"query": "x"}, id="s")])


setup(script_endless)
report = agent.NOTES_RESEARCHER.run("a task")
check("a researcher that never stops still returns a report", report == "report from what I found", report)

print(f"\n{sum(PASSED)}/{len(PASSED)} passed")
