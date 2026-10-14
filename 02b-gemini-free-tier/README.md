# 02b - Same Agent, Different Model (Gemini free tier)

## Goal

Run stage 02 for free, and learn which parts of an agent depend on the model
provider and which don't.

## What I learned

- The agent pattern doesn't depend on the provider. Tools, approval gate,
  sandbox and loop logic are copied unchanged from stage 02.
- Only two things changed: the wrapper around tool schemas, and the shape of
  the model call and reply.
- Read docs and installed SDK code instead of trusting memory: Google's newest
  API (Interactions) differs from what most tutorials show.

## Architecture

Identical to stage 02. Only the "model" box changed:

```
model (Gemini 3.8 Flash) ──function_call──► my loop ──► approval? ──► tool
          ▲                                                       │
          └──────────────── function_result ◄─────────────────────┘
```

## Claude vs Gemini, side by side

| Concept | Claude (stage 02) | Gemini Interactions (02b) |
|---|---|---|
| SDK / key | `anthropic`, `ANTHROPIC_API_KEY` | `google-genai`, `GEMINI_API_KEY` |
| Tool schema | `{"name", "description", "input_schema"}` | `{"type": "function", "name", "description", "parameters"}` |
| History | `messages=[...]` | `input=[...]` (list of steps) |
| User turn | `{"role": "user", "content": "..."}` | `{"type": "user_input", "content": [{"type": "text", ...}]}` |
| Model asks for a tool | `tool_use` block: `id`, `name`, `input` | `function_call` step: `id`, `name`, `arguments` |
| I send the result | `tool_result`: `tool_use_id`, `content`, `is_error` | `function_result`: `call_id`, `result`, `is_error` |
| Done? | `stop_reason == "end_turn"` | no `function_call` steps in the reply |
| Final text | text blocks | `interaction.output_text` |

Gemini can also keep the history **on its server** (`previous_interaction_id`)
so you don't resend it. We use `store=False` and resend everything, so the
`history` list stays the agent's state, as in every stage so far.

## Setup

1. https://aistudio.google.com > **Get API key** > **Create API key** (free, no card).
2. Save it without typing it in a terminal: Start menu > "Edit environment
   variables for your account" > New > Name `GEMINI_API_KEY`, Value: the key.
3. Open a **new** PowerShell window, then:

```powershell
cd C:\Users\temp1\claude-learn\ai-agent-lab
.venv\Scripts\python -m pip install -r 02b-gemini-free-tier\requirements.txt
```

## Run

Read-only question about the lab (no approvals needed):

```powershell
.venv\Scripts\python 02b-gemini-free-tier\agent.py --root . "How does 01-agent-from-scratch/agent.py decide when to stop looping?"
```

Writing and running, in a sandbox:

```powershell
.venv\Scripts\python 02b-gemini-free-tier\agent.py --root C:\Users\temp1\claude-learn\sandbox "Create hello.py that prints today's date, then run it"
```

Offline tests: `python test_approval.py` (same as stage 02).

**Free tier caveats:** daily and per-minute limits (you'll see a clear message
if you hit one), and Google may use free-tier content to improve its products.
Only point it at the lab or the sandbox, never at confidential code.

## Experiments to try

1. Run the same task on stage 02 (Claude) and 02b (Gemini), if you ever have
   both. Compare tool choices and step counts.
2. Decline a write with a reason. Does Gemini adapt the same way?
3. Print `history` at the end and compare it with Claude's `messages`.

## Check your understanding

1. Which sections of `agent.py` changed from stage 02, and which didn't? Why?
2. Gemini offers server-side history (`previous_interaction_id`). What would we
   gain, and what would we lose for learning?
3. Why does the loop keep only the steps after the last input we sent?

## Problems I encountered

- The Interactions API raises errors from a private module (`_gaos`), not
  `google.genai.errors`, so the first error handler caught nothing. Fixed by
  reading the HTTP status code from the exception.
- The SDK's docs page didn't say whether replies repeat earlier steps. The
  loop appends only steps after the last input, which is correct either way.

## What I would improve

- A provider-agnostic `call_model()` so one `agent.py` can switch providers with a flag.

## Next step

Run it with a real free key, then stage 03.
