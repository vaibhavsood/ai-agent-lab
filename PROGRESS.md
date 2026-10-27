# AI Agent Engineering Progress

## Checklist

- [x] Set up the lab repo and documentation structure
- [x] Push the lab to GitHub (github.com/vaibhavsood/ai-agent-lab)
- [ ] 01: Run the from-scratch agent on a real folder and read its trace
- [ ] 01: Answer the understanding questions in `01-agent-from-scratch/README.md`
- [x] 02: Build tools with side effects + human approval (offline tests pass)
- [ ] 02: Run it with the real model and try the decline experiments
- [x] 02b: Build the stage 02 agent on Gemini's free tier (offline tests pass)
- [x] 02b: Get a free Gemini key and run it for real (read-only question on the lab)
- [ ] 02b: Run the write/approve/decline experiments in the sandbox
- [x] 03: Downloads organizer (plan-then-execute), offline tests pass
- [x] 04: Context & memory (incl. API timeouts + retries); memory tested live, compaction unit-tested
- [x] 05: RAG over the lab, cited answers, tested live
- [ ] 06: Structured outputs & reasoning
- [ ] 07: MCP
- [ ] 08: Multi-agent
- [ ] 09: Guardrails & security
- [ ] 10: Evals & observability
- [ ] 11: Frameworks & SDKs (LangGraph + agent SDKs)
- [ ] 12: Local models (Ollama)
- [ ] 13: Production

## Projects

1. File investigation agent (01)
2. File agent that writes and runs commands, with approval (02, 02b on Gemini)
3. Downloads organizer, plan-then-execute (03, side stage)
4. **My agent** (04 onward): the 02b agent, upgraded every stage

## Major lessons

- 2026-09-24: An agent is LLM + tools + loop. The model can only ask; my code decides what runs.
- 2026-09-24: The model only sees a tool's name, description, and schema. The description is the interface.
- 2026-10-08: Human approval is an `if` in my loop. A "no" goes back to the model as a tool_result, so it can adapt.
- 2026-10-14: Switching provider changed only the tool-schema wrapper and the model call. Tools, approval and loop logic stayed the same.
- 2026-10-14: First real run. Right answer, made-up line numbers, because read_file returns no line numbers. Agents are only as accurate as their tools' output.

- 2026-10-26: Plan-then-execute: review one validated plan instead of many prompts; the model decides, code acts, and everything can be undone.
- 2026-10-26: Always set timeouts on API calls. Without one, a provider that never answers hangs the agent forever.

- 2026-10-27: The model decides when to remember; the tool description is the trigger. Long-term memory is just a file loaded into the system instruction.
- 2026-10-27: Don't trust provider metrics blindly: Gemini's input-token count leaves out tool results. Measure what you send.

- 2026-10-27: RAG = find the few relevant passages by meaning, answer only from them, cite them. Keyword and semantic search fail differently; combine them.
- 2026-10-27: Free tiers have no availability guarantee: enforce your own deadlines and fall back to another model.

## Next milestone

Stage 06: structured outputs & reasoning.
