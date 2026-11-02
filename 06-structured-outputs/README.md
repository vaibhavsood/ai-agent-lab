# 06 - Structured Outputs & Reasoning

## Goal

Make the agent's answers data that code can check, instead of prose to be
trusted, and measure what "thinking" buys.

## What I learned

- **Schema:** a precise description of the output's shape. Here:
  `found_in_notes` (bool), `answer` (string), `citations` [{`source`, `quote`}].
- **Structured output:** with `response_format` + `response_mime_type`, the
  API makes the final reply valid JSON in that shape. It works **together
  with tools**: the model still calls `search_notes`, then answers in JSON.
- **Verify, don't trust:** code reads the actual file lines / PDF page each
  citation points at and checks the quote is really there (ignoring case,
  whitespace and markdown; paraphrases fail).
- **Self-correction:** failed citations go back to the model once, as
  feedback; if it fails again, the answer is shown with honest ✗ marks.
- **Thinking levels** (`minimal` / `low` / `medium` / `high`): more thinking
  cost ~2,000 tokens per question and added a few seconds, but did NOT
  improve accuracy on lookup questions. Thinking helps multi-step reasoning.
- **One run is an anecdote:** free-tier latency (36-106 s spikes) swamped the
  differences. Proper measurement = evaluation (stage 10).

## Architecture

```
 question ─► agent loop (search_notes, read_file, ...)  every call: response_format = ANSWER_SCHEMA
                │
                ▼ final reply = JSON {found_in_notes, answer, citations[{source, quote}]}
          answers.check_answer: for each citation, read that file:lines / PDF page,
                                is the quote really there?
                │
        all ✓ ──► show answer + "citations: 2/2 verified"
        any ✗ ──► send failures back to the model (once) ──► re-check ──► show with ✓/✗
```

## Files

- `answers.py`: the schema, JSON parsing, citation checking, feedback, display.
- `agent.py`: stage 05 + schema on every call, verification + one fix, `--thinking`,
  `--show-thinking`. Reuses `05-rag/index.json`.
- `compare_thinking.py`: the thinking-level experiment.
- `test_structured.py`: 19 offline tests (model mocked).

## Run

```powershell
cd C:\Users\temp1\claude-learn\ai-agent-lab\06-structured-outputs
..\.venv\Scripts\python agent.py --root ..
..\.venv\Scripts\python agent.py --root .. --thinking high --show-thinking
..\.venv\Scripts\python compare_thinking.py
```

## Experiment: thinking levels (2026-11-02, one run each)

| Level | Thinking tokens / question | Citations verified | "World Cup" (not in notes) |
|---|---|---|---|
| minimal | 0 | 7/7 | found_in_notes: false, no citations |
| low | 0-31 | 6/6 | same |
| high | 750-2,178 | 5/5 | same |

Healthy calls took 3-10 s (high ~9 s, low ~3 s); three calls took 36-106 s
because of free-tier slowdowns at minimal/low, unrelated to thinking.

## Problems I encountered

- A test "failed" because my test was wrong: the checker allows 3 lines of
  slack and the quote was within it. Fixed the test, not the code.
- `import agent` loaded **stage 05's** agent.py because I put `05-rag` first
  on Python's search path. Same file name, different folder. Put it last.
- PowerShell quoting broke inline Python; scripts in files are more reliable.

## What I would improve

- Verify that each claim in `answer` is supported, not just that quotes exist
  (a correct quote can still be attached to a wrong claim).
- Run the thinking comparison many times per question (stage 10).

## Check your understanding

1. Why check citations against the actual files rather than trusting `found_in_notes`?
2. Why allow only ONE self-correction attempt?
3. Why didn't more thinking help on these questions? What kind would it help?

## Next step

Stage 07: MCP.
