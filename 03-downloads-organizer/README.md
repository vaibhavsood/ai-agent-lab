# 03 - Downloads Organizer (plan, then execute)

A side stage. The task (tidying a fake Downloads folder) isn't something I'd
use, but four ideas from it carry into later stages.

## What I learned

- **Plan, then execute:** one review of a whole plan beats 28 y/n prompts
  that I'd stop reading.
- **A plan is a tool call:** `propose_plan` has a strict schema, so code can
  validate it (no overwrites, no leaving the folder) before I see it.
- **The model decides, my code acts:** the model never moves a file. It also
  has no delete tool at all (least privilege).
- **Code for exact work, model for judgment:** code finds duplicates by
  hashing contents; the model decides folder names.
- **Reversibility:** every move is logged; `--undo` puts everything back.

## Architecture

```
scan_folder() ─► propose_plan([...]) ─► code validates ─► I review the whole plan
                        ▲                                      │         │
                        └──── feedback (rejected) ◄────────────┘      approved
                                                                         ▼
                                                       code moves files + undo log
```

## Run

```powershell
python make_fake_downloads.py                       # creates ..\..\sandbox\fake-downloads
python agent.py --root ..\..\sandbox\fake-downloads
python agent.py --root ..\..\sandbox\fake-downloads --undo
python test_organizer.py                            # offline tests, no key needed
```

## What happened in the live run (2026-10-26, Gemini free tier)

- Step 1: `scan_folder` returned 28 files with duplicates marked by code.
- Step 2: one `propose_plan` with 28 moves into 8 folders. All 3 duplicates
  went to `_Duplicates` (using the code's `duplicate_of` field). It guessed
  `random_download` (no extension) was a document.
- I rejected it (scripted) with feedback: screenshots in `Images/Screenshots`,
  resumes and cover letters in `Job`. Nothing moved.
- Step 3: the revision request **never returned**. The process sat idle,
  waiting forever, until stopped.

## Problems I encountered

- **No timeout on API calls.** A provider that never answers hangs the agent
  forever. Fix in stage 04: timeouts + retries.
- Python buffers prints when output goes to a pipe, so a scripted run looked
  frozen. `python -u` shows output immediately.
- Undo missed parent folders of nested paths (`Images/Screenshots`). Fixed,
  and covered by a test.

## Check your understanding

1. Why validate the plan in code before showing it to the human?
2. Why does the model get `duplicate_of` from code instead of finding duplicates itself?
3. What does leaving out a delete tool protect against?
