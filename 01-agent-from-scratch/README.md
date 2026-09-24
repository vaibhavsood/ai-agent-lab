# 01 - Agent from Scratch

## Goal

Build the smallest real agent with no framework: an LLM that can investigate
files by calling tools in a loop until it can answer.

## What I learned

(Fill in after running it.)

## Architecture

```
User task
   │
   ▼
┌──────────────┐   tool_use    ┌────────────────────────┐
│  Claude API  │ ────────────► │ my code runs the tool  │
│ (decides)    │ ◄──────────── │ list / read / search   │
└──────┬───────┘  tool_result  └────────────────────────┘
       │   (repeats until stop_reason == "end_turn", max 15 steps)
       ▼
 Final answer with file:line citations
```

## Tools

| Tool | What it does |
|------|--------------|
| `list_files(path)` | Recursive file listing under the root |
| `read_file(path)` | Full text of one file (truncated at 50k chars) |
| `search_files(query)` | Case-insensitive grep, returns `path:line: text` |

All tools are read-only and sandboxed to `--root`. Tools that change things
(`write_file`, `run_command`) wait for stage 02, when we add human approval.

## Implementation

`agent.py` has three sections, labeled in the code:

1. **Tools**: plain Python functions.
2. **Tool schemas**: JSON descriptions sent to the model so it knows the tools exist.
3. **Agent loop**: call the model; if `stop_reason == "tool_use"`, run each
   requested tool, send all results back in one message, and repeat.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Get an API key at https://console.anthropic.com and set it for this terminal:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

## Run

```bash
python agent.py --root C:\path\to\a\repo "Find where configuration is loaded and summarize how it works"
```

The console shows each step: what the model said, which tool it called, and a
preview of the result. That trace is the agent loop in action.

## Experiments to try

1. Give it a task that needs 3+ steps (search -> read -> read again). Count the steps.
2. Make a tool description vague (e.g. `"Search"`). Does tool choice get worse?
3. Set `MAX_STEPS = 2`. What happens on a hard task?
4. Ask it to read `../../something`. Watch the error go back to the model and how it reacts.
5. Print `messages` at the end and look at the raw history the model saw.

## Check your understanding

1. Where is the agent's state stored, and what happens to it between API calls?
2. How does the model know which tools exist?
3. What happens if a tool raises an exception?
4. Which lines make this an *agent* and not a chatbot?

## Problems I encountered

## What I would improve

## Next step

Stage 02: add `write_file` and `run_command`, with a y/n approval before anything runs.
