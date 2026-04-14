# Logbook: resolution

One row per skill change, recording which feedback patterns were addressed, what changed, and whether a later session confirmed the fix worked.

## Address

`<workspace>/resolution.csv`

Same workspace as `feedback.csv` (e.g. the root of your current project). The two logbooks are always co-located — resolution rows reference feedback IDs by the `feedback_ids` column.

CLI: `python scripts/retro_db.py <command> <workspace>`

## Storage

CSV — flat columns, low write volume (one row per skill change), append-only except for the `verified_by_session_id` back-fill. Upgrade to SQLite only if cross-logbook joins with feedback.csv become too slow or if resolution history needs multi-column aggregation.

## Schema

| Column | Type | Required | Semantics |
|---|---|---|---|
| `resolution_id` | string | yes | Auto-incremented stable identifier: `r001`, `r002`, … Never reused or reordered. |
| `feedback_ids` | string | yes | Space-separated list of `feedback_id` values this resolution addresses, e.g. `f001 f003 f007`. All referenced IDs must exist in `feedback.csv` — enforced at write time. |
| `status` | enum | yes | `open` — change described but not yet applied. `addressed` — change applied to the skill. `wont_fix` — decided not to change; requires a reason in `notes`. |
| `what_changed` | string | conditional | One to three sentences describing exactly what was changed in the skill. Required when `status=addressed`. Empty for `open` and `wont_fix`. |
| `addressed_at` | ISO 8601 UTC | conditional | Timestamp set automatically when `status=addressed`. Empty otherwise. Never edited. |
| `verified_by_session_id` | string | no | ID of a later session that ran the updated skill and confirmed the fix worked. Empty until verified. This is the only column patched after row creation. |
| `notes` | string | conditional | Free text. Required when `status=wont_fix` — document the reason so the same feedback doesn't trigger re-evaluation unnecessarily. Optional otherwise. |

## Identity

Auto-incremented sequential ID with `r` prefix and zero-padded to three digits: `r001`, `r002`, … Assigned by `retro_db.py resolution_add` and stable — rows are never reordered or renumbered.

## Partial rows

Empty string for optional fields. `verified_by_session_id` starts empty and is back-filled later. `notes` is optional except for `wont_fix`. `addressed_at` is set automatically when `status=addressed`, empty otherwise. All conditionally-required fields are enforced at write time by `resolution_add`.

## Corrections

`verified_by_session_id` is the only column patched in place after row creation — it is a back-fill, not a correction. All other columns are immutable after creation.

If a resolution row's `what_changed` or `feedback_ids` are wrong, append a new resolution row with corrected values and note the superseded ID in `notes`. Do not edit the original — the history of what you thought you fixed matters when the same feedback resurfaces.

## Queries

All queries run against `<workspace>/resolution.csv` via the CLI.

### List all open resolutions
```bash
python retro_db.py resolution_list <workspace> --status open
```

### List addressed but unverified resolutions
```bash
python retro_db.py resolution_list <workspace> --status addressed
# Then check which rows have verified_by_session_id empty
```

### Show full detail for one resolution
```bash
python retro_db.py resolution_show <workspace> r001
```

### Python one-liner — find addressed but unverified rows
```python
import csv
rows = list(csv.DictReader(open('resolution.csv')))
unverified = [r['resolution_id'] for r in rows
              if r['status'] == 'addressed' and not r.get('verified_by_session_id')]
print(unverified)
```

### Python one-liner — which feedback IDs have no resolution
```python
import csv
fb = {r['feedback_id'] for r in csv.DictReader(open('feedback.csv'))}
resolved = set()
for r in csv.DictReader(open('resolution.csv')):
    resolved.update(r['feedback_ids'].split())
print(fb - resolved)  # feedback with no resolution row
```

## Validation

A row is **complete for `addressed` status** when: `what_changed` is non-empty and `addressed_at` is set. Enforced by `resolution_add`.

A row is **complete for `wont_fix` status** when: `notes` is non-empty with the reason. Enforced by `resolution_add`.

A row is **verified** when: `verified_by_session_id` is non-empty.

A resolution is **a guess** when: `status=addressed` and `verified_by_session_id` is empty for more than one subsequent session that used the same skill. Either commit to running the updated skill and verifying, or add a note accepting unverified status.

## Actions

### verify-resolution

- **Purpose:** Back-fill `verified_by_session_id` when a later session confirms the fix worked.
- **Readiness check:** `status=addressed` (only addressed resolutions can be verified).
- **Effect:** Patches `verified_by_session_id` on the resolution row.
- **Command:**
  ```bash
  python retro_db.py resolution_verify <workspace> r001 --session-id <id>
  ```

If a subsequent session shows the fix did not work (`sentiment=improve` for the same pattern), write a new resolution row rather than updating the old one. The old row records what was tried; the new row records what was tried next.

## Governance

- **Owner:** Single user (the skill practitioner). Responsible for deciding what counts as "addressed" and when to verify.
- **Access:** Single writer. Read access is open — any Claude session with workspace file access can call `resolution_list` and `resolution_show`.
- **Conflict resolution:** Last-write-wins. File locking via `retro_db.py` prevents concurrent corruption. Git history is the audit trail.
- **Lifetime:** Indefinite — co-located with `feedback.csv`, archived together when the workspace is retired.
- **Sunset rule:** Same as `feedback.csv` — export a summary snapshot before archiving. Include a count of addressed vs. unverified resolutions so future skill work can see what was left open.
