# AI Agent Engineering Lab

This is my AI Agent Engineering Lab. You are my pair programmer and tutor.
I want to understand what we build, not merely receive working code.

## How to work with me

- Build complexity progressively: raw LLM -> one tool -> agent loop -> multiple tools
  -> state -> memory -> MCP -> frameworks. Do not jump ahead or add a framework,
  vector DB, or multi-agent setup unless the current stage calls for it.
- Before coding a new stage, explain the architecture in a few sentences and a small diagram.
- After coding, explain each important component, then ask me 2-3 questions to test my understanding.
- Do not hide implementation details. If I ask, show the raw request/response between the LLM and the tools.
- Prefer the smallest implementation that teaches the concept.

## After every meaningful feature

1. Update the code.
2. Explain what changed.
3. Update that stage's README.md (use the template in `templates/stage-README.md`).
4. Add a short entry to `journal/YYYY-MM-DD.md` (template in `templates/journal.md`).
5. Update the architecture diagram in the stage README if it changed.
6. Add any new concepts to `knowledge/agent-concepts.md`.
7. Update `PROGRESS.md`.
8. Tell me what I should understand before moving to the next stage.

Journal entries must reflect what I actually did and learned. Draft them, and I will review them.
Don't invent insights I didn't have.

## Conventions

- Python. I don't pay for API usage, so runnable stages must work on a **free** model:
  Gemini free tier (`google-genai`, `gemini-3.8-flash`, key in `GEMINI_API_KEY`).
  Claude versions (`anthropic`, `claude-opus-5`) are kept for comparison.
- Free-tier Gemini data may be used by Google: only run agents on the lab or a sandbox folder.
- API keys come from environment variables. Never hardcode or commit them.
- Each stage is a self-contained folder `NN-name/` with `agent.py`, `README.md`, `requirements.txt`.
