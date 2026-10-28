# 05 - RAG (Retrieval-Augmented Generation)

## Goal

Make the agent a knowledge assistant for my notes: answer questions about
this lab from my own files, with `[file:lines]` citations, instead of from
training data.

## What I learned

- **Embeddings** turn text into vectors; similar meaning gives similar vectors.
  "How does the agent avoid running forever?" lands near `MAX_STEPS`.
- **RAG = retrieve, then generate.** Find the few relevant passages, give
  only those to the model, and make it cite them.
- **Agentic RAG:** retrieval is a tool the model chooses to call. It can
  search again with better words if the first results are weak (it did,
  rewriting a query to `MAX_STEPS`).
- **Keyword and semantic search fail differently.** Keywords found the exact
  "loop forever" line; embeddings found the right topics but ranked that line
  lower. Production systems combine both (hybrid search).
- **Chunking matters:** splitting at every heading made 386 tiny chunks;
  merging small sections gave 229 chunks of ~574 chars.
- **Deduplicate:** my 6 near-identical `agent.py` copies would otherwise fill
  every result list with the same code.
- **An index goes stale.** It must be rebuilt when notes change; the agent warns
  when files are newer than the index.
- **Free-tier limits are per item, not per request:** 100 embeddings/minute,
  and each text in a batch counts.

## Architecture

```
 INDEXING  (python index.py)
 lab .md/.py ─► chunk (~800 chars, merge tiny sections, dedupe)
            ─► embed each chunk (gemini-embedding-2, 768 numbers)
            ─► index.json  (text + vector + file:lines)

 ASKING  (python agent.py)
 question ─► model calls search_notes(query)
          ─► embed query ─► cosine similarity vs every chunk ─► top 5 + sources
          ─► model answers from those passages, citing [file:lines]
             (may search again with a better query)
```

## Tools

Stage 04's tools plus `search_notes(query, top_k)`.

## Implementation

- `rag.py`: chunking, embedding (rate-limited, one vector per text enforced),
  index save/load, staleness check, cosine search, result formatting.
- `index.py`: builds `index.json` (git-ignored; rebuild, don't commit).
- `agent.py`: stage 04 + `search_notes`, plus a system prompt that requires
  citations and labels general-knowledge answers.
- Reliability fixes found in this stage (see Problems): hard deadline per
  API call, automatic fallback model.

## Run

```powershell
cd C:\Users\temp1\claude-learn\ai-agent-lab\05-rag
..\.venv\Scripts\python index.py          # ~2-3 min on the free tier
..\.venv\Scripts\python agent.py --root ..
..\.venv\Scripts\python test_rag.py       # 13 offline tests
```

## PDFs

- Put PDFs in `ai-agent-lab/library/` (git-ignored: PDFs are often personal,
  copyrighted or large), then re-run `index.py`.
- `pypdf` extracts text **per page**; chunks are cited by page:
  `[library/paper.pdf p.3]`.
- **Scanned PDFs** (images of text) have nothing to extract: they're skipped
  with a warning. Supporting them would need OCR.
- `read_file` can open a whole PDF (with `--- page N ---` markers).
- Sample: `python make_sample_pdf.py` writes `library/agent-glossary.pdf`,
  defining terms that are NOT in my notes (ReAct, context rot, tool poisoning).
- Free tier: PDF text goes to Google. Nothing confidential.

## Experiments

| Question | Result |
|---|---|
| What did I learn about tool descriptions? | Correct, cited `knowledge/agent-concepts.md:53-70` |
| Why did we switch Gemini models? | Correct, cited my journal; impossible from training data |
| How does the agent avoid running forever? | Searched twice (rewrote query to `MAX_STEPS`), correct, 3 citations; one citation was stale |
| Capital of France? | "Paris", labeled as general knowledge, no search |

## Problems I encountered

- **A list of strings gave ONE embedding for all of them.** Each text must be
  its own `Content`. Now enforced: a count mismatch raises an error.
- **429 rate limit** while indexing. Pacing (90 per minute) + wait-as-told retries.
- `search_files` matched inside the 1.7 MB `index.json`. Now skipped.
- **The SDK timeout didn't stop hangs** (calls sat 10+ min with no error).
  Fixed with our own hard deadline (`with_deadline`, a background thread).
- **`gemini-3.6-flash` stopped answering** even "2+2", while
  `gemini-3.5-flash-lite` answered in ~1s. Fixed with automatic fallback
  after 2 timeouts.

## What I would improve

- Hybrid search (keywords + embeddings).
- Incremental re-indexing (only changed files).
- A vector database once there are many thousands of chunks.

## Check your understanding

1. Why does semantic search find "avoid running forever" passages that don't contain those words?
2. Why make retrieval a tool instead of always retrieving before answering?
3. What goes wrong if you don't rebuild the index after editing notes?

## Next step

Stage 06: structured outputs & reasoning.
