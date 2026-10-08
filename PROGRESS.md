# AI Agent Engineering Progress

## Checklist

- [x] Set up the lab repo and documentation structure
- [x] Push the lab to GitHub (github.com/vaibhavsood/ai-agent-lab)
- [ ] 01: Run the from-scratch agent on a real folder and read its trace
- [ ] 01: Answer the understanding questions in `01-agent-from-scratch/README.md`
- [x] 02: Build tools with side effects + human approval (offline tests pass)
- [ ] 02: Run it with the real model and try the decline experiments
- [ ] 03: Computer agent
- [ ] 04: Memory + state
- [ ] 05: MCP
- [ ] 06: LangGraph
- [ ] 07: Evaluation
- [ ] 08: Production deployment

## Projects

1. File investigation agent (01)
2. File agent that writes and runs commands, with approval (02)

## Major lessons

- 2026-09-24: An agent is LLM + tools + loop. The model can only ask; my code decides what runs.
- 2026-09-24: The model only sees a tool's name, description, and schema. The description is the interface.
- 2026-10-08: Human approval is an `if` in my loop. A "no" goes back to the model as a tool_result, so it can adapt.

## Next milestone

Get an API key and run Agent #1 against one of my own repos.
