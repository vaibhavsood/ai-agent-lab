# 08 - Multi-agent: a lead, researchers and a reviewer

## Goal

Split my knowledge assistant into a small team and learn what that buys and
what it costs: delegation, context isolation, parallel work, per-agent
permissions, and an LLM reviewer next to the code checks from stage 06.

## What I learned

- A sub-agent is just a tool whose function runs another agent loop
  (`agent_as_tool`). The loop from stage 02b didn't change; it got packaged
  into an `Agent` class so there can be several.
- **Context isolation** is the main benefit. In the live run the researchers
  held ~6,200 tokens of passages; the lead's history stayed ~2,500 tokens.
- **Parallel fan-out:** the lead split a two-part question into two tasks in
  one step, and they ran at the same time.
- **The costs are real.** Without a budget, researchers kept searching until
  `max_steps` and returned nothing: 159k tokens for one question. With a
  budget and a forced report on the last step: 17k.
- **Handoffs lose detail:** quotes got paraphrased between researcher and
  lead (3/6 citations verified); code caught it and the lead fixed it.
- Code checks what code can (quotes exist in the files); the reviewer judges
  what code can't (is the answer supported, complete, on topic).

## Architecture

```
                         you
                          │ question
                          ▼
                 ┌───────────────────┐  tools: ask_notes_researcher, ask_web_researcher, remember
                 │ LEAD              │  keeps the chat history; never searches itself
                 └──┬─────────────┬──┘
     task A (self-  │             │  task B      several calls in ONE step run IN PARALLEL
     contained text)▼             ▼
        ┌────────────────┐  ┌────────────────┐
        │notes_researcher│  │notes_researcher│  fresh, EMPTY history per task, step budget
        │ search_notes   │  │ search_notes   │  tools: only search_notes, read_note (MCP)
        │ read_note      │  │ read_note      │
        └───────┬────────┘  └───────┬────────┘
                │ short report: findings + [source] + exact quotes
                └────────┬──────────┘
                         ▼
                 LEAD writes JSON answer ──► code verifies citations (stage 06, one fix)
                         │
                         ▼
                 ┌──────────────┐  no tools; gets question + reports + draft
                 │   REVIEWER   │  rejects → lead revises once
                 └──────┬───────┘
                        ▼
                       you
```

`web_researcher` (tool: `fetch`) works like `notes_researcher`, for web pages.

## Tools

| Agent | Tools (enforced in `Agent.dispatch`) |
|-------|--------------------------------------|
| lead | `ask_notes_researcher`, `ask_web_researcher`, `remember` |
| notes_researcher | `search_notes`, `read_note` (lab-notes MCP server from stage 07) |
| web_researcher | `fetch` (official MCP fetch server) |
| reviewer | none (JSON verdict: `approved`, `problems`) |

No write or command tools in this stage: agents run in parallel threads, and
`input()` approval prompts from several threads at once don't work. Only MCP
servers marked `readOnly` in my config are used.

## Implementation

```
python agent.py                 # lead + researchers + reviewer
python agent.py --no-review     # skip the reviewer
python test_multi_agent.py      # 13 offline checks with a fake model
```

Reuses stage 07's `mcp_client.py` and `answers.py`, and stage 07's
`lab_server.py` (which searches stage 05's `index.json`).

## Key code

- `class Agent`: name + instructions + tool list + loop. `run(task)` starts
  an empty history (sub-agent); `run(task, history)` continues the lead's chat.
- `Agent._run_calls`: one call runs directly; several run in a
  `ThreadPoolExecutor`. `pool.map` keeps the results in call order, so each
  `function_result` matches its `call_id`.
- `agent_as_tool(...)`: registers a tool whose function is `worker.run(task)`
  and saves the report for the reviewer.
- Step budget: the prompt says "at most 4 tool calls", and on the last step
  code asks for the report instead of throwing the work away.
- `answer_question`: lead → citation check (one fix) → reviewer (one revision).
- `TeamUsage`: tokens and calls per agent, plus how much the sub-agents read
  that never entered the lead's context.
- Two threads can call the same MCP server at once: both submit coroutines to
  the one event loop in `mcp_client`, which matches replies by JSON-RPC `id`.

## Experiments

### Experiment 1: two-part question, before and after the step budget

"What did I learn about tool descriptions, and why did I switch from Claude to Gemini?"

| | No budget | Budget + forced report |
|---|---|---|
| Researcher runs | 4 (2 returned nothing) | 3 |
| Researcher model calls | 27 | 7 |
| Total tokens | 159,205 | 17,406 |
| Citations | 6/6 | 3/6, then 6/6 after one fix |

Both runs: the lead sent the two parts in parallel, the reviewer approved,
and gemini-3.6-flash timed out so the fallback model took over.

## Problems I encountered

1. Researchers never stopped searching; `max_steps` discarded all their work.
2. Quotes got paraphrased on the way from researcher to lead.
3. A test stored a reference to the history list, which the agent kept
   appending to, so the test saw later steps too.

## What I would improve

- Compare with the single stage 07 agent on the same questions (tokens, time,
  quality); stage 10 (evals) is the place for that.
- A cheaper model for researchers (`Agent(model=...)` is already there).
- The reviewer sees only the current question, not the chat, so follow-ups
  can confuse it.

## Next step

Stage 09: guardrails and security (prompt injection, permissions, output checks).
