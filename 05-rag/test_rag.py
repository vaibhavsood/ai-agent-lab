"""
Offline tests for the RAG engine. No API key: embeddings are faked.

    python test_rag.py
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).parent))
import agent
import rag


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    if not cond:
        sys.exit(1)


VOCAB = ["loop", "steps", "stop", "memory", "remember", "football", "gemini", "model", "tool"]


def fake_embed(texts, is_query):
    """Crude 'embedding': count vocabulary words. Similar topics -> similar vectors."""
    return [rag._normalize([t.lower().count(w) + 0.01 for w in VOCAB]) for t in texts]


# 1. chunking splits at markdown headings and keeps line numbers
md = "# Title\nintro line here about things\n\n## Loop\nthe loop stops after max steps\n\n## Memory\nremember facts in memory.md\n"
chunks = rag.chunk_file("notes.md", md, min_chars=0)
check("markdown is split at headings", [c["text"].splitlines()[0] for c in chunks] == ["# Title", "## Loop", "## Memory"])
check("line numbers point at the right lines", (chunks[1]["start"], chunks[1]["end"]) == (4, 6))

# 2. long sections are split to stay near max_chars
long_md = "# Big\n" + "\n".join(f"line {i} with some filler text" for i in range(100))
check("long sections are split into several chunks", len(rag.chunk_file("big.md", long_md, max_chars=300)) > 5)

check("tiny sections are merged instead of split", len(rag.chunk_file("notes.md", md, min_chars=300)) == 1)

# 3. collect_chunks skips memory.md and .venv
root = Path(tempfile.mkdtemp())
rag.MIN_CHARS = 0  # tiny test files: split at every heading
(root / "a.md").write_text(md)
(root / "b.md").write_text(md)  # an exact copy, like the per-stage agent.py files
(root / "memory.md").write_text("# Private\nVaibhav supports Real Madrid football club.")
(root / ".venv").mkdir()
(root / ".venv" / "x.py").write_text("def secret():\n    return 'should not be indexed at all'\n")
collected = rag.collect_chunks(root)
sources = {c["source"] for c in collected}
check("memory.md and .venv are never indexed", "memory.md" not in sources and not any(".venv" in s for s in sources))
check("duplicate chunks are indexed once, with the copy noted", sources == {"a.md"} and collected[1]["also_in"] == ["b.md:4-6"])

# 4. search ranks the passage with the closest meaning first, with a citable source
index = rag.build_index(root, fake_embed)
top = rag.search(index, "when does the loop stop?", fake_embed, top_k=3)
check("the right passage ranks first", top[0]["text"].startswith("## Loop"))
check("results carry file:line sources", rag.format_results(top).startswith("[1] a.md:4-6"))

# 5. the embedder refuses a response with the wrong number of vectors
bad_client = NS(models=NS(embed_content=lambda **k: NS(embeddings=[NS(values=[1.0, 0.0])])))
try:
    rag.gemini_embedder(bad_client)(["one", "two", "three"], is_query=False)
    check("one vector for three texts is an error", False)
except RuntimeError as e:
    check("one vector for three texts is an error", "got 1" in str(e))

# 6. the agent's tool works with and without an index
agent.INDEX, agent.EMBED = None, fake_embed
check("search_notes without an index says how to build one", "index.py" in agent.search_notes("loop"))
agent.INDEX = index
check("search_notes returns cited passages", "a.md:4-6" in agent.search_notes("when does the loop stop?"))

# 7. a call that hangs forever is abandoned at the deadline and retried
import time
real_sleep = time.sleep  # agent.time IS the time module, so patching it below affects everyone
calls = []


class HangOnceClient:
    def __init__(self):
        self.interactions = self

    def create(self, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            real_sleep(60)  # simulate the hang (the SDK timeout never fires)
        return NS(output_text="ok")


agent.TIMEOUT_SECONDS = -4  # deadline = TIMEOUT_SECONDS + 5 = 1 second
agent.time.sleep = lambda s: None  # skip the backoff wait in the test
t = time.time()
r = agent.call_model(HangOnceClient(), input=[])
check("a hung call is abandoned at the deadline and the retry succeeds", r.output_text == "ok" and len(calls) == 2 and time.time() - t < 5)

# 8. two timeouts in a row switch to the fallback model
models_used = []


class DeadModelClient:
    def __init__(self):
        self.interactions = self

    def create(self, **kwargs):
        models_used.append(kwargs["model"])
        if kwargs["model"] == "dead-model":
            raise TimeoutError("no answer")
        return NS(output_text="answered by fallback")


agent.MODEL, agent.FALLBACK_MODEL = "dead-model", "backup-model"
r = agent.call_model(DeadModelClient(), input=[])
check("after 2 timeouts the fallback model answers", r.output_text == "answered by fallback"
      and models_used == ["dead-model", "dead-model", "backup-model"] and agent.MODEL == "backup-model")

print("\nAll stage 05 checks passed.")
