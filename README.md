# skill-retrospective

A structured feedback loop for improving Claude skills over time. Two CSV logbooks, four phases, one loop.

Captures what went well and what could improve across skill sessions — groups recurring patterns, prioritizes fixes, and tracks resolutions. Lives next to the skills it describes, not in an external tracker.

## Setup

### Requirements

- Python 3 (for the retro database script)

### Claude Desktop

Works in both **Chat** and **Cowork** modes — the plugin installs once and is available everywhere.

**In Chat mode:**

1. Click **Customize** in the left sidebar
2. Open the **Directory** and select the **Plugins** tab
3. Switch to the **Personal** tab, click **"+"** → **Add marketplace**
4. Enter `ydmitry/skill-retrospective` and click **Sync**

**In Cowork mode:**

1. Click **Customize** in the left sidebar
2. Next to **Personal plugins**, click **"+"** → **Add marketplace**
3. Enter `ydmitry/skill-retrospective` and click **Sync**

**Upload manually:**

1. Go to [github.com/ydmitry/skill-retrospective](https://github.com/ydmitry/skill-retrospective) → green **Code** button → **Download ZIP**
2. Rename the file from `.zip` to `.plugin`
3. In the same plugin menu above, choose **Upload plugin** instead and select the file

### Claude Code (CLI)

```shell
/plugin marketplace add ydmitry/skill-retrospective
/plugin install skill-retrospective@ydmitry-skill-retrospective
```

Or from a local clone:

```bash
git clone https://github.com/ydmitry/skill-retrospective.git
claude --plugin-dir ./skill-retrospective
```

### Initialize a workspace

The workspace is the project folder where `feedback.csv` and `resolution.csv` will live. Use that project's root directory.

```bash
python scripts/retro_db.py init <workspace>
```

## Usage

### At the end of a skill session — Phase 1

Invoke the skill to collect feedback while the session is still fresh:

```
/retro
```

Claude will ask which skill was used, collect observations one at a time, and write structured rows to `feedback.csv`.

Or write a row directly via CLI:

```bash
python scripts/retro_db.py feedback_add <workspace> \
  --skill deep-ideation \
  --session-id "2026-04-13-miro-export" \
  --sentiment improve \
  --what-happened "Scorer exited after 8 of 118 ideas without error" \
  --evidence "run log line 42: 'Scored 8 ideas, done'"
```

### In a dedicated retro session — Phases 2 and 3

```
/retro group       # Group ungrouped feedback rows
/retro prioritize  # Set priority on each group
```

Or use the CLI directly:

```bash
# See ungrouped rows
python retro_db.py feedback_list <workspace> --ungrouped

# Assign a group
python retro_db.py feedback_set_group <workspace> f001 scorer-reliability

# Summarize all groups
python retro_db.py groups_summary <workspace>

# Set priority (1 = low, 5 = fix first)
python retro_db.py feedback_set_priority <workspace> --group scorer-reliability --priority 5
```

### After changing a skill — Phase 4

```
/retro resolve
```

Or via CLI:

```bash
python retro_db.py resolution_add <workspace> \
  --feedback-ids "f001 f007 f012" \
  --what-changed "Scorer now reads cohort size via describe() before starting; loops in batches of 20 until all ideas are scored." \
  --status addressed
```

### After confirming a fix worked

```bash
python retro_db.py resolution_verify <workspace> r001 --session-id "2026-04-20-verify-run"
```

## The four phases

```
Phase 1 (per session)
  → append feedback rows: sentiment + what_happened + evidence
  → group and group_priority are empty

Phase 2 (retro session)
  → agent reads all ungrouped feedback
  → proposes clusters, you review and approve
  → fills group column on feedback rows

Phase 3 (same retro session)
  → for each group, agent summarizes the pattern and proposes a priority
  → you set group_priority (1–5, where 5 = fix this first)

Phase 4 (after making the change)
  → append resolution row pointing at feedback_ids
  → set status=addressed, fill what_changed

Later
  → next session using the updated skill writes feedback
  → if sentiment=good for that scenario, back-fill verified_by_session_id
  → if sentiment=improve, the fix didn't work — write another resolution row
```

## Schema

### feedback.csv

| Column | Description |
|---|---|
| `feedback_id` | Auto-incrementing: `f001`, `f002`, … |
| `skill_name` | e.g. `deep-ideation` |
| `session_id` | The chat session that produced the feedback |
| `created_at` | ISO 8601 UTC |
| `sentiment` | `good` or `improve` |
| `what_happened` | One sentence: the observed behavior |
| `evidence` | Quote, line ref, file path, or row ID — required |
| `group` | Pattern tag assigned in Phase 2, e.g. `scorer-reliability` |
| `group_priority` | 1–5 set in Phase 3. 5 = fix first. Empty for `good` rows. |

### resolution.csv

| Column | Description |
|---|---|
| `resolution_id` | Auto-incrementing: `r001`, `r002`, … |
| `feedback_ids` | Space-separated list of feedback IDs this addresses |
| `status` | `open`, `addressed`, or `wont_fix` |
| `what_changed` | 1–3 sentences describing the skill change. Required for `addressed`. |
| `addressed_at` | ISO 8601 UTC, set automatically when status=addressed |
| `verified_by_session_id` | Back-filled when a later session confirms the fix worked |
| `notes` | Free text. Required for `wont_fix` — document the reason. |

## All CLI commands

```bash
python retro_db.py init <workspace>
python retro_db.py feedback_add <workspace> --skill <name> --session-id <id> --sentiment good|improve --what-happened "..." --evidence "..."
python retro_db.py feedback_list <workspace> [--ungrouped] [--skill <name>] [--sentiment good|improve]
python retro_db.py feedback_show <workspace> <feedback_id>
python retro_db.py feedback_set_group <workspace> <feedback_id> <group>
python retro_db.py feedback_set_priority <workspace> --group <group> --priority 1-5
python retro_db.py groups_summary <workspace>
python retro_db.py resolution_add <workspace> --feedback-ids "f001 f002" --what-changed "..." [--status open|addressed|wont_fix] [--notes "..."]
python retro_db.py resolution_verify <workspace> <resolution_id> --session-id <id>
python retro_db.py resolution_list <workspace> [--status open|addressed|wont_fix]
python retro_db.py resolution_show <workspace> <resolution_id>
```

## Requirements

- Python 3
- No external dependencies — stdlib only
