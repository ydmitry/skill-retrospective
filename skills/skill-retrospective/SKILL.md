---
name: skill-retrospective
description: >
  Four-phase skill retrospective loop. Collects structured feedback at the end of skill sessions,
  groups recurring patterns, prioritizes fixes, and tracks resolutions across sessions.
  Use at the end of any session that used a skill to capture what went well or what could improve,
  or in a dedicated retro session for grouping and prioritization.
  Also use when the user says "let's retro", "review how the skill went", "capture feedback",
  "what went wrong", "log this observation", or "record a resolution".
license: MIT
metadata:
  author: ydmitry
  version: "1.0.0"
---

# Skill Retrospective

Structured feedback loop for improving Claude skills over time. Four phases: collect → group → prioritize → resolve.

## Core Principles

1. **Evidence required** — every feedback row must have a concrete reference (quote, line number, file path). An observation without evidence is not actionable.
2. **One observation per row** — don't bundle three things into one row. The resolution side references individual IDs.
3. **Propose, don't auto-apply** — in Phases 2 and 3, propose groupings and priorities, wait for approval before writing.
4. **Both sides or neither** — feedback without resolutions is a graveyard. Always prompt to write resolutions when changes are made.

## The Script

All data operations go through the CLI. The script lives alongside this skill:

```
python scripts/retro_db.py <command> <workspace> [options]
```

The workspace is the project folder where `feedback.csv` and `resolution.csv` will live — use that project's root directory.

If the workspace has not been initialized, run `init` first:
```
python scripts/retro_db.py init <workspace>
```

## Phase Detection

When the user runs `/retro`, ask:

```
AskUserQuestion:
  question: "Which phase?"
  header: "Retro"
  options:
    - "Phase 1 — Collect feedback from this session"
    - "Phase 2 — Group ungrouped feedback"
    - "Phase 3 — Prioritize groups"
    - "Phase 4 — Record a resolution"
```

If args were passed (e.g. `/retro group`), map them directly:
- `group` → Phase 2
- `prioritize` → Phase 3
- `resolve` → Phase 4
- no arg → Phase 1

---

## Phase 1 — Feedback Collection

**Goal:** Append structured feedback rows for the current session before context is lost.

### Steps

1. **Identify the workspace.** Ask: "Which workspace?" — suggest the current working directory. Confirm before proceeding.

2. **Check init.** Verify feedback.csv exists. If not, run `init` first.

3. **Identify the skill.** Ask which skill was used in this session (e.g. `deep-ideation`, `ultra-brainstorming`). If multiple skills were used, collect feedback for each separately.

4. **Get the session ID.** Use the current session identifier (visible in conversation metadata, or ask the user: "What should I use as the session ID? (e.g. today's date + topic)").

5. **Collect observations — one at a time.** Ask:

```
AskUserQuestion:
  question: "Anything notable about this session — what went well or what could improve?"
  header: "Observation"
  options:
    - "Something went well"
    - "Something could improve"
    - "Both"
    - "Nothing notable — skip"
```

For each observation, ask:
- **What happened?** (one sentence, the observed behavior — not a solution)
- **Evidence?** (quote from the output, line number, file path, row ID — required)
- **Sentiment?** good | improve (if not already clear from context)

Then write the row:
```bash
python scripts/retro_db.py feedback_add <workspace> \
  --skill "<skill_name>" \
  --session-id "<session_id>" \
  --sentiment good|improve \
  --what-happened "<one sentence>" \
  --evidence "<concrete reference>"
```

6. **Loop.** After each row, ask: "Anything else?" Stop when the user says no.

7. **Confirm.** Show a summary of rows added. If none were added, confirm that's intentional.

### Rules
- Never skip evidence. If the user can't name a concrete reference, ask them to look at the output first.
- `what_happened` describes behavior, not a solution. "Scorer exited after 8 ideas" not "Scorer should loop until all ideas are covered."
- `sentiment` is strictly `good` or `improve`. Don't use other values.

---

## Phase 2 — Grouping

**Goal:** Assign group tags to ungrouped feedback rows, in a dedicated retro session.

### Steps

1. **Confirm workspace and skill filter.** Ask if they want to group all skills or one skill at a time.

2. **Read ungrouped rows:**
```bash
python scripts/retro_db.py feedback_list <workspace> --ungrouped
```

3. **Propose clusters.** Read the ungrouped rows and identify recurring patterns — same failure mode across sessions, or consistent wins. Present proposed groups:

```
Proposed groupings:
  scorer-reliability — f001, f007, f012  (scorer exits early in 3 sessions)
  id-collision       — f002              (row IDs overwritten)
  naming-wins        — f004, f009        (strong naming output)

Approve, adjust, or suggest different groupings?
```

4. **Wait for approval** before writing anything.

5. **Apply groups** for each approved grouping:
```bash
python scripts/retro_db.py feedback_set_group <workspace> f001 scorer-reliability
# repeat for each row
```

6. **Confirm.** Show remaining ungrouped count.

### Rules
- Group names should be lowercase-hyphenated, short (1-3 words), describing the pattern not the fix.
- `good` rows get groups too — they are the baseline for what's working.
- Don't auto-apply without approval.

---

## Phase 3 — Prioritization

**Goal:** Set group_priority (1–5) on each group, and identify which to act on.

### Steps

1. **Show groups summary:**
```bash
python scripts/retro_db.py groups_summary <workspace>
```

2. **For each group, present a one-line pattern summary and proposed priority.**

3. **Wait for user to approve or adjust each priority.**

4. **Write priorities** for approved groups:
```bash
python scripts/retro_db.py feedback_set_priority <workspace> --group scorer-reliability --priority 5
```

5. **Summarize actionable groups** (improve rows with priority ≥ 3).

### Rules
- Priority scale: 5 = fix this first (correctness/recurrence), 1 = minor/low-value
- `good` rows generally don't get a priority number — they're reference, not action items
- Don't set priority without user approval

---

## Phase 4 — Resolution

**Goal:** Record what changed in the skill and which feedback IDs it addresses.

### Steps

1. **Ask what was changed.** "Which skill was updated, and what changed?"

2. **Show relevant feedback:**
```bash
python scripts/retro_db.py feedback_list <workspace> --skill <name>
python scripts/retro_db.py groups_summary <workspace>
```

3. **Ask which feedback IDs this resolution addresses.** Space-separated: "f001 f003 f007"

4. **Verify the description.** Ask for 1–3 sentences on what changed.

5. **Write the resolution:**
```bash
python scripts/retro_db.py resolution_add <workspace> \
  --feedback-ids "f001 f003 f007" \
  --what-changed "<1-3 sentences>" \
  --status addressed \
  [--notes "<optional>"]
```

6. **Remind about verification:** "When you next run the updated skill and confirm the fix worked, run: `python scripts/retro_db.py resolution_verify <workspace> <resolution_id> --session-id <id>`"

### wont_fix path
If the user decides not to fix something, use `--status wont_fix` and require `--notes` with the reason.

---

## Anti-Patterns to Refuse

- **Feedback without evidence.** If the user can't provide a reference, prompt them to find one before writing the row.
- **Grouping without review.** Always present proposed groups before calling `feedback_set_group`.
- **`wont_fix` without notes.** Enforce the reason. Ask before writing.
- **Skipping resolution.** If the user mentions they changed a skill, prompt them to write a resolution row.
- **Verifying an unaddressed resolution.** `resolution_verify` only works on `status=addressed`. Enforce this.
