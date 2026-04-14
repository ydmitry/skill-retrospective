# Logbook: feedback

One observation per row from skill sessions — what went well or what could improve — so recurring patterns can be grouped, prioritized, and acted on across sessions.

## Address

`<workspace>/feedback.csv`

The workspace is a project root directory supplied at call time (e.g. the root of your current project). The `skill_name` column distinguishes between skills when a single workspace covers multiple skills.

CLI: `python scripts/retro_db.py <command> <workspace>`

## Storage

CSV — flat columns, short string values, append-heavy writes, single user. Openable in Excel, greppable from bash, diffable in git. Upgrade to SQLite if row volume exceeds a few thousand or cross-logbook joins with resolution.csv become necessary.

## Schema

| Column | Type | Required | Semantics |
|---|---|---|---|
| `feedback_id` | string | yes | Auto-incremented stable identifier: `f001`, `f002`, … Never reused or reordered. |
| `skill_name` | string | yes | The skill observed, e.g. `deep-ideation`. Used to group and filter feedback across skills in one workspace. |
| `session_id` | string | yes | Human-readable session identifier, e.g. `2026-04-13-miro-export`. Ties observations back to the conversation they came from. |
| `created_at` | ISO 8601 UTC | yes | Timestamp set automatically at row creation. Never edited. |
| `sentiment` | enum | yes | `good` or `improve`. Strictly two values — free text breaks grouping and counting. |
| `what_happened` | string | yes | One sentence describing the observed behavior. Not a solution — what the skill did, not what it should do. |
| `evidence` | string | yes | A concrete reference: a quote from output, a line number, a file path, a row ID. A row with no evidence is an opinion, not actionable feedback. |
| `group` | string | no | Pattern tag assigned during Phase 2 grouping, e.g. `scorer-reliability`. Empty until grouped. Lowercase-hyphenated, 1–3 words describing the pattern not the fix. |
| `group_priority` | integer 1–5 | no | Set during Phase 3 prioritization on all rows in a group. 5 = fix this first. Empty for `good` rows and unactioned groups. |

## Identity

Auto-incremented sequential ID with `f` prefix and zero-padded to three digits: `f001`, `f002`, … The ID is assigned by `retro_db.py feedback_add` and is stable — rows are never reordered or renumbered.

## Partial rows

Empty string for missing fields. `group` and `group_priority` start empty by design — they are filled in later phases. All other columns are required at creation time and enforced by `feedback_add`.

## Corrections

`group` and `group_priority` are patched in place — these are the only columns edited after row creation, and patching is simpler than appending correction rows for a single-user workflow. All other columns (`feedback_id`, `skill_name`, `session_id`, `created_at`, `sentiment`, `what_happened`, `evidence`) are immutable after creation. If an immutable field is wrong, append a new row with the corrected values and note the superseded ID in `evidence`.

## Queries

All queries run against `<workspace>/feedback.csv` via the CLI.

### List all ungrouped rows
```bash
python retro_db.py feedback_list <workspace> --ungrouped
```

### List by skill
```bash
python retro_db.py feedback_list <workspace> --skill deep-ideation
```

### List by sentiment
```bash
python retro_db.py feedback_list <workspace> --sentiment improve
```

### Show full detail for one row
```bash
python retro_db.py feedback_show <workspace> f007
```

### Summarize all groups (count, sentiment split, priority)
```bash
python retro_db.py groups_summary <workspace>
```

### Python one-liner — count improve rows per skill
```python
import csv; from collections import Counter
rows = list(csv.DictReader(open('feedback.csv')))
print(Counter(r['skill_name'] for r in rows if r['sentiment']=='improve'))
```

## Validation

A row is **complete for Phase 1** when: `feedback_id`, `skill_name`, `session_id`, `created_at`, `sentiment`, `what_happened`, and `evidence` are all non-empty. Enforced at write time by `feedback_add`.

A row is **ready for Phase 3** when: `group` is non-empty.

A group is **actionable** when: `group_priority` is set and `sentiment=improve`.

Find rows missing evidence (should be zero if using the CLI):
```python
import csv
rows = list(csv.DictReader(open('feedback.csv')))
print([r['feedback_id'] for r in rows if not r.get('evidence')])
```

Find ungrouped rows:
```python
print([r['feedback_id'] for r in rows if not r.get('group')])
```

## Actions

No direct external system push is defined for this logbook. The downstream action is: identify high-priority groups → make changes to the skill → record resolutions in `resolution.csv`.

If a future need arises to trigger a skill improvement agent from unresolved high-priority groups, that action belongs here.

## Governance

- **Owner:** Single user (the skill practitioner). Responsible for schema changes and grouping decisions.
- **Access:** Single writer. Read access is open — any Claude session with workspace file access can read and call `feedback_add`.
- **Conflict resolution:** Last-write-wins. File locking via `retro_db.py` prevents concurrent corruption. Git history is the audit trail.
- **Lifetime:** Indefinite — accumulates across all sessions using any skill in the workspace. Archive per workspace when the associated project concludes.
- **Sunset rule:** When a project workspace is retired, export a `groups_summary` snapshot to a markdown doc, then archive or delete the CSV. Do not merge feedback across unrelated projects into one file.
