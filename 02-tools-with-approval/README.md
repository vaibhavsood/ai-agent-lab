# 02 - Tools with Approval

## Goal

Let the agent change things (write files, run commands) without giving up
control: every change waits for a human "yes".

## What I learned

- Approval is not a model feature. It's an `if` in my own loop, between the
  model's request and the tool running.
- A "no" isn't a crash. It goes back to the model as a normal `tool_result`
  (with `is_error: true`), and my reason steers its next step.
- The path sandbox protects file tools, but `run_command` can reach anything my
  user account can. For commands, approval is the only guard.
- Agent code can be tested offline by mocking the parts I don't control (here,
  the human's `input()`).

## Architecture

```
model ──tool_use──► my loop
                      │
          read-only tool? ──yes──► run it
                      │
                      no (write_file / run_command)
                      ▼
            show the human exactly what it wants
                      │
            y ────────┴──────── n (+ optional reason)
            ▼                    ▼
         run it        tool_result: "User declined. Reason: ..."
            │                    │
            └──────► back to the model, which adapts
```

## Tools

| Tool | Side effects | Approval |
|------|--------------|----------|
| `list_files`, `read_file`, `search_files` | None | No |
| `write_file(path, content)` | Creates or overwrites a file inside `--root` | **Yes**, shows path, new/OVERWRITE, first 20 lines |
| `run_command(command)` | Anything the shell can do, 60s timeout | **Yes**, shows the exact command |

## Implementation

What changed from stage 01 (`agent.py`):

1. Two new tool functions: `write_file` and `run_command`.
2. `NEEDS_APPROVAL = {"write_file", "run_command"}`: one set decides which tools are gated.
3. `ask_approval()`: prints what the agent wants, asks y/n, and on "n" asks for an optional reason.
4. `run_tool()`: checks approval before running a gated tool. **The loop itself is unchanged.**
5. The system prompt says: if declined, don't retry the same action; adapt.
6. Tool descriptions tell the model the shell (`cmd.exe` on Windows) and the 60s timeout,
   so it doesn't write Linux commands or start a server that never exits.

## Key code

```python
if name in NEEDS_APPROVAL:
    approved, reason = ask_approval(name, args)
    if not approved:
        msg = "The user declined this action."
        return (msg + f" Their reason: {reason}" if reason else msg), True
return fn(**args), False
```

## Setup and run

Same as stage 01 (venv + `ANTHROPIC_API_KEY`). Use a throwaway folder as `--root`:

```bash
mkdir C:\Users\temp1\claude-learn\sandbox
python agent.py --root C:\Users\temp1\claude-learn\sandbox "Create hello.py that prints the date, then run it"
```

Offline tests (no API key needed):

```bash
python test_approval.py
```

## Experiments to try

1. Approve everything for a small task. Count the tool calls.
2. Decline a `write_file` with the reason "use a different filename". Does it adapt?
3. Decline with **no** reason. What does the model do with less information?
4. Remove the "do not retry" sentence from `SYSTEM` and decline repeatedly. Does it loop?
5. Ask it to delete a file. Which tool does it choose, given there's no `delete_file`?

## Check your understanding

1. The model never sees the word "approval" in any API field. How does it find out you said no?
2. Why does the sandbox protect `write_file` but not `run_command`?
3. Why return a decline as a `tool_result` instead of stopping the agent?

## Problems I encountered

- First version printed half the approval box before discovering an invalid path.
  Fixed by validating the path before printing anything.

## What I would improve

- Show a real diff when overwriting, not just the new content.
- "Always allow" per tool for the session, so safe repeated commands don't need a prompt each time.
- An allowlist of safe commands (`dir`, `python --version`) that skip approval.

## Next step

Stage 03: a computer agent for a real personal task (e.g. organizing Downloads),
where approval and planning really matter.
