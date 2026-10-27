# 04 - Context & Memory

## Goal

Give the agent memory (within a chat and across restarts), keep its context
from growing forever, and stop it from hanging on a slow API.

## What I learned

- **Short-term memory = history.** A chat loop just keeps appending to the
  same history list across my messages.
- **Long-term memory = a file the model writes to.** `remember(fact)` appends
  to `memory.md`; at startup the file goes into the system instruction.
- **The model decides when to remember**, guided only by the tool description
  and the system prompt. It saved my name and my football team without being
  asked. It's judgment, so it isn't guaranteed.
- **Compaction:** when history gets too big, ask the model to summarize it,
  then replace the history with the summary.
- **Timeouts + retries:** retry timeouts, 429 and 5xx with backoff (2s, 4s, 8s);
  never retry a 400, since a bad request won't get better.
- **Don't trust provider metrics blindly.** Gemini's reported input tokens
  leave out function results. Verified with an experiment, so compaction uses
  our own estimate (~4 characters per token).
- **The newest free model is the slowest.** `gemini-3.8-flash` took 100+ s for
  "2+2" on the free tier; `gemini-3.6-flash` took ~7 s.
- The folder limits what the agent can **do**, not what the model **knows**. It
  answers general questions from training data (unsourced, possibly outdated).

## Architecture

```
 memory.md ──(loaded at startup)──► system instruction
     ▲
     └── remember(fact) ◄── model decides
                                   │
 you ──► chat loop ──► history ──► call_model (timeout 90s, retries) ──► tools
                          │
              ~tokens > --compact-at ? ──► summarize ──► history = [summary]
```

## Tools

Same as 02b (list, read, search, write*, run*) plus `remember(fact)`.
(* = needs approval)

## Run

```powershell
cd C:\Users\temp1\claude-learn\ai-agent-lab
.venv\Scripts\python 04-context-and-memory\agent.py --root C:\Users\temp1\claude-learn\sandbox
```

Options: `--compact-at 2000` (watch compaction happen), `--model gemini-3.5-flash-lite` (faster).
Chat commands: `/memory`, `/compact`, `/exit`. Offline tests: `python test_context.py`.

## Experiments I ran

1. **Codeword test (scripted):** "remember blue-falcon" → `remember` called;
   fresh restart → answered from `memory.md` with no tool calls.
2. **Hints without saying "remember" (me, interactive):** it saved my name and
   that I support Real Madrid.
3. **Off-topic question:** it answered a football question from training data.
   No tool was used.
4. **Token experiment:** same 8,000-char file as user text = 2,218 input
   tokens; as a function_result = 169 reported, yet the model quoted a line
   from it exactly. The report undercounts; the model sees everything.

## Problems I encountered

- `gemini-3.8-flash` timed out repeatedly on the free tier. Switched to 3.6.
- The compaction trigger never fired because the API undercounts tool results.
  Fixed with our own estimate.
- **Open:** one live run hung overnight despite the 90 s timeout. Unconfirmed
  hypothesis: the timeout applies between chunks of the response, not to the
  whole call. **Confirmed and fixed in stage 05** (`with_deadline` + fallback model);
  this stage's snapshot still has the bug.
- Compaction is unit-tested but hasn't been seen triggering live yet.

## What I would improve

- A `/remember <fact>` command for guaranteed saves, and a `forget` tool.
- Show which facts were loaded at startup.

## Check your understanding

1. What's the difference between short-term and long-term memory in this agent?
2. Why can't we use the API's input-token count to decide when to compact?
3. Why is a 400 error not retried?

## Next step

Stage 05: RAG over this lab's notes, answers with citations.
