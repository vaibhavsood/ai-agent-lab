# AI Agent Engineering Lab

My hands-on path from "LLM + one tool" to a production-grade personal agent.
Each stage is a working agent plus notes on what I learned building it.

## Foundations (done)

| # | Stage | Concept | Status |
|---|-------|---------|--------|
| 01 | [Agent from scratch](01-agent-from-scratch/) | Tool calling + the agent loop, no framework | Built, not yet run |
| 02 | [Tools with approval](02-tools-with-approval/) | write_file, run_command, human approval | Built, offline-tested |
| 02b | [Gemini free tier](02b-gemini-free-tier/) | Same agent, different provider: what changes and what doesn't | Runs on the free tier |
| 03 | [Downloads organizer](03-downloads-organizer/) | Side stage: plan-then-execute, least privilege, undo | Built, tested; live run hung (no API timeout) |

## Roadmap: one agent, upgraded every stage

From 04 on, each stage adds a capability to the **same agent** (starting from
02b). Each stage folder is a snapshot, so I can compare before and after.

**The agent's job: a personal knowledge assistant for my own projects and notes.**
Point it at a folder (this lab first), ask questions, get answers with sources,
have it remember my preferences and make changes with my approval. Its first
real user is this lab: "What did I learn about tool descriptions?", "Which
stages have open questions?", "Draft today's journal."

| # | Stage | What the agent gains |
|---|-------|----------------------|
| 04 | Context & memory | Remembers across runs, summarizes long history, counts tokens, timeouts + retries |
| 05 | RAG | Embeddings, chunking, vector search, cited answers over my notes and docs |
| 06 | Structured outputs & reasoning | JSON-schema outputs, thinking levels, plan-first |
| 07 | MCP | Use existing MCP servers, then expose my tools as an MCP server |
| 08 | Multi-agent | Orchestrator + sub-agents (researcher, reviewer); when not to |
| 09 | Guardrails & security | Prompt injection, permissions, output checks |
| 10 | Evals & observability | Test sets, LLM-as-judge, tracing, cost tracking |
| 11 | Frameworks & SDKs | Rebuild in LangGraph; compare Claude Agent SDK, Google ADK, OpenAI Agents SDK |
| 12 | Local models | Same agent on Ollama, offline; compare |
| 13 | Production | Telegram/web interface, deployment, logging, rate limits |

Optional later: browser/computer use, voice agents, fine-tuning.

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
