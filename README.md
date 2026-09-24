# AI Agent Engineering Lab

My hands-on path from "LLM + one tool" to a production-grade personal agent.
Each stage is a working agent plus notes on what I learned building it.

## Stages

| # | Stage | Concept | Status |
|---|-------|---------|--------|
| 01 | [Agent from scratch](01-agent-from-scratch/) | Tool calling + the agent loop, no framework | In progress |
| 02 | Tools with side effects | write_file, run_command, human approval | |
| 03 | Computer agent | Real personal tasks (e.g. organize Downloads) | |
| 04 | Memory + state | Persisting across sessions | |
| 05 | MCP | Standardized tool integration | |
| 06 | LangGraph | Rebuild the same agent with a framework and compare | |
| 07 | Evaluation | Measuring whether the agent is good | |
| 08 | Production agent | Telegram/web interface, observability, deployment | |

## Layout

```
ai-agent-lab/
├── CLAUDE.md          instructions for Claude Code (tutor mode + doc rules)
├── PROGRESS.md        checklist, major lessons, next milestone
├── NN-stage/          one folder per stage: agent.py, README.md
├── journal/           short daily logs (5-10 min each)
├── knowledge/         my own agent-engineering reference
├── templates/         README and journal templates
└── articles/          polished write-ups, later
```

## Workflow

Build -> notes -> stage README -> lessons learned -> article.
I build with Claude Code, it drafts the docs, I review and correct them.
