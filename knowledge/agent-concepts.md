# Agent Concepts

My own reference. Add to it whenever something clicks.

## Tool calling

An LLM does not execute functions. It returns a structured request:

```json
{"type": "tool_use", "id": "toolu_01...", "name": "search_files", "input": {"query": "root squash"}}
```

My application runs the function and sends the result back, linked by the same id:

```json
{"type": "tool_result", "tool_use_id": "toolu_01...", "content": "nfs/export.c:88: ..."}
```

The model learns what tools exist only from the `name`, `description`, and
`input_schema` I send with every request. The description is the tool's UI for the model.

---

## Agent loop

LLM -> tool call -> observation -> LLM -> tool call -> observation -> ... -> answer

The API response's `stop_reason` drives the loop:
- `tool_use`: run the requested tools, append results, call the LLM again
- `end_turn`: the model is done; return its text

What separates an agent from a chatbot: the model takes actions and uses their
results to decide the next action.

---

## State

In the simplest agent, state is just the `messages` list. Every call re-sends
the whole history; the API itself remembers nothing between calls.

---

## The model can only ask

The model can't do anything by itself. It can only request a tool call. My
code decides whether to run it. If it asks for a tool that doesn't exist, my
code replies "Unknown tool". My code is always in control, and this is the
basis of agent safety.

---

## Tool descriptions are the interface

The model never sees a tool's code. It only sees the `name`, `description`,
and `input_schema`. A vague description means wrong or missed tool calls.
The description is the tool's user interface, and the model is the user.

---

## Agents adapt, scripts don't

A script follows a fixed plan. An agent decides each step from the previous
result. Example: while building this lab, Claude Code hit three errors in a
row (Store Python redirecting AppData, path too long, file not found). Each
error came back as a tool result, and it chose a different approach each
time. No fixed plan would have predicted those failures.

---

## Human-in-the-loop approval

Approval lives in my loop, not in the model. Before a tool with side effects
runs, my code shows the human the exact action and asks y/n.

- **Yes**: run the tool as normal.
- **No**: don't run it. Send back a `tool_result` like
  `"The user declined this action. Their reason: ..."` with `is_error: true`.

The model never sees an "approval" feature. It just sees a tool result and
adapts, so the human becomes one more source of tool results. A reason makes
the decline useful: "use greet.py instead" steers the next step.

---

## Sandboxes have limits

A path check protects file tools (`write_file` can't leave `--root`). It does
**not** protect `run_command`: a shell command can touch anything my user
account can. Know which guard protects which tool.

---

## Testing agents offline

Mock the parts I don't control. Replacing `input()` with a function that
returns scripted answers tests the approval gate without a human or an API
key. The same trick works for the model: script its `tool_use` replies.

---

## Guardrails (so far)

- Max step limit, so a confused model can't loop forever
- Path sandboxing, so tools can't read outside an allowed root
- Tool errors are returned to the model (`is_error: true`) instead of crashing,
  so it can recover
- Human approval before any tool with side effects (stage 02)
- Timeouts on commands, so a hung program can't freeze the agent (stage 02)
