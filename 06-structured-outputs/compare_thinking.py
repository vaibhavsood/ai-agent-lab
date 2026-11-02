"""
Experiment: what does more "thinking" buy? Same questions, different thinking
levels; compare time, thinking tokens, and whether citations verify.

    python compare_thinking.py                     # minimal, low, high
    python compare_thinking.py --levels low high

Uses the lab index from stage 05. Free tier: ~12 questions = ~30 model calls.
"""

import argparse
import io
import time
from contextlib import redirect_stdout
from pathlib import Path

from google import genai

import agent
import rag

QUESTIONS = [
    "What did I learn about tool descriptions?",
    "Why did we switch Gemini models?",
    "What is tool poisoning?",                   # only in the glossary PDF
    "Who won the 2022 football World Cup?",      # NOT in my notes
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--levels", nargs="+", default=["minimal", "low", "high"])
    args = parser.parse_args()

    agent.INDEX = rag.load_index(agent.INDEX_FILE)
    agent.EMBED = rag.gemini_embedder(genai.Client())
    agent.ROOT = Path(agent.INDEX["root"])
    client = genai.Client()

    rows = []
    for level in args.levels:
        agent.THINKING_LEVEL = level
        for q in QUESTIONS:
            usage = agent.Usage()
            agent.LAST_RESULT = None
            t = time.time()
            with redirect_stdout(io.StringIO()) as log:  # keep the table readable
                try:
                    agent.run_turn(client, [], q, usage)
                except Exception as e:
                    print(f"ERROR {type(e).__name__}")
            secs = time.time() - t
            r = agent.LAST_RESULT
            if r is None:
                rows.append((level, q, secs, usage.thinking, "-", "-", "no answer"))
                continue
            checks = r["checks"]
            verified = f"{sum(ok for _, ok, _ in checks)}/{len(checks)}"
            searches = log.getvalue().count("tool call: search_notes")
            rows.append((level, q, secs, usage.thinking, r["answer"]["found_in_notes"], verified,
                         f"{searches} search(es){', fixed once' if r['retried'] else ''}"))
            print(f"{level:8} {secs:5.1f}s  {q[:45]}", flush=True)

    print(f"\n{'level':8} {'time':>6} {'think':>6} {'in notes':>9} {'cites ok':>9}  question / notes")
    for level, q, secs, think, found, verified, note in rows:
        print(f"{level:8} {secs:5.1f}s {think:6} {str(found):>9} {verified:>9}  {q[:40]} ({note})")


if __name__ == "__main__":
    main()
