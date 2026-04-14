#!/usr/bin/env python3
"""
Skill Retro DB — CSV-based skill retrospective tracking.

Two logbooks, four phases, one loop. Captures what went well and what could improve
across skill sessions, groups patterns, prioritizes fixes, and tracks resolutions.

feedback.csv columns:
    feedback_id, skill_name, session_id, created_at, sentiment,
    what_happened, evidence, group, group_priority

resolution.csv columns:
    resolution_id, feedback_ids, status, what_changed,
    addressed_at, verified_by_session_id, notes

Usage:
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
"""

import argparse
import csv
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

try:
    import fcntl

    def _acquire_lock(lock_fd, shared):
        fcntl.flock(lock_fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)

    def _release_lock(lock_fd):
        fcntl.flock(lock_fd, fcntl.LOCK_UN)

except ImportError:
    import msvcrt

    def _acquire_lock(lock_fd, shared):
        lock_fd.seek(0)
        while True:
            try:
                msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.05)

    def _release_lock(lock_fd):
        try:
            lock_fd.seek(0)
            msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass


FEEDBACK_FILENAME = "feedback.csv"
FEEDBACK_LOCK_FILENAME = "feedback.csv.lock"
FEEDBACK_COLUMNS = [
    "feedback_id", "skill_name", "session_id", "created_at",
    "sentiment", "what_happened", "evidence", "group", "group_priority",
]

RESOLUTION_FILENAME = "resolution.csv"
RESOLUTION_LOCK_FILENAME = "resolution.csv.lock"
RESOLUTION_COLUMNS = [
    "resolution_id", "feedback_ids", "status", "what_changed",
    "addressed_at", "verified_by_session_id", "notes",
]

READ_ONLY_COMMANDS = frozenset({
    "feedback_list", "feedback_show", "groups_summary",
    "resolution_list", "resolution_show",
})

FEEDBACK_COMMANDS = frozenset({
    "feedback_add", "feedback_list", "feedback_show",
    "feedback_set_group", "feedback_set_priority", "groups_summary",
})

RESOLUTION_COMMANDS = frozenset({
    "resolution_add", "resolution_verify", "resolution_list", "resolution_show",
})


# ── locking ──────────────────────────────────────────────────────────────────

def _seed_lock(lock_path):
    if not os.path.exists(lock_path):
        try:
            with open(lock_path, "x") as f:
                f.write("\0")
        except FileExistsError:
            pass


@contextmanager
def locked_feedback(workspace, *, shared=False):
    lock_path = os.path.join(workspace, FEEDBACK_LOCK_FILENAME)
    _seed_lock(lock_path)
    lock_fd = open(lock_path, "r+")
    try:
        _acquire_lock(lock_fd, shared)
        yield
    finally:
        _release_lock(lock_fd)
        lock_fd.close()


@contextmanager
def locked_resolution(workspace, *, shared=False):
    lock_path = os.path.join(workspace, RESOLUTION_LOCK_FILENAME)
    _seed_lock(lock_path)
    lock_fd = open(lock_path, "r+")
    try:
        _acquire_lock(lock_fd, shared)
        yield
    finally:
        _release_lock(lock_fd)
        lock_fd.close()


# ── I/O ──────────────────────────────────────────────────────────────────────

def read_feedback(workspace):
    path = os.path.join(workspace, FEEDBACK_FILENAME)
    if not os.path.exists(path):
        print(f"Error: No feedback.csv at {path}. Run 'init' first.", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_feedback(workspace, rows):
    path = os.path.join(workspace, FEEDBACK_FILENAME)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FEEDBACK_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_resolution(workspace):
    path = os.path.join(workspace, RESOLUTION_FILENAME)
    if not os.path.exists(path):
        print(f"Error: No resolution.csv at {path}. Run 'init' first.", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_resolution(workspace, rows):
    path = os.path.join(workspace, RESOLUTION_FILENAME)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESOLUTION_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ── ID generation ─────────────────────────────────────────────────────────────

def _next_feedback_id(rows):
    nums = []
    for r in rows:
        fid = r.get("feedback_id", "")
        if fid.startswith("f"):
            try:
                nums.append(int(fid[1:]))
            except ValueError:
                pass
    return f"f{max(nums) + 1:03d}" if nums else "f001"


def _next_resolution_id(rows):
    nums = []
    for r in rows:
        rid = r.get("resolution_id", "")
        if rid.startswith("r"):
            try:
                nums.append(int(rid[1:]))
            except ValueError:
                pass
    return f"r{max(nums) + 1:03d}" if nums else "r001"


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_init(args):
    ws = args.workspace
    os.makedirs(ws, exist_ok=True)

    fb_path = os.path.join(ws, FEEDBACK_FILENAME)
    if os.path.exists(fb_path):
        print(f"feedback.csv already exists at {fb_path}")
    else:
        with open(fb_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FEEDBACK_COLUMNS).writeheader()
        print(f"Created {fb_path}")

    res_path = os.path.join(ws, RESOLUTION_FILENAME)
    if os.path.exists(res_path):
        print(f"resolution.csv already exists at {res_path}")
    else:
        with open(res_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=RESOLUTION_COLUMNS).writeheader()
        print(f"Created {res_path}")

    print(f"\nWorkspace ready: {ws}")
    print(f"Columns — feedback : {', '.join(FEEDBACK_COLUMNS)}")
    print(f"Columns — resolution: {', '.join(RESOLUTION_COLUMNS)}")


def cmd_feedback_add(args):
    rows = read_feedback(args.workspace)
    fid = _next_feedback_id(rows)
    row = {
        "feedback_id": fid,
        "skill_name": args.skill,
        "session_id": args.session_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sentiment": args.sentiment,
        "what_happened": args.what_happened,
        "evidence": args.evidence,
        "group": "",
        "group_priority": "",
    }
    rows.append(row)
    write_feedback(args.workspace, rows)
    print(f"Added {fid}: [{args.sentiment}] {args.what_happened[:72]}")


def cmd_feedback_list(args):
    rows = read_feedback(args.workspace)
    if args.ungrouped:
        rows = [r for r in rows if not r.get("group")]
    if args.skill:
        rows = [r for r in rows if r.get("skill_name") == args.skill]
    if args.sentiment:
        rows = [r for r in rows if r.get("sentiment") == args.sentiment]
    if not rows:
        print("No feedback rows match.")
        return
    print(f"{'ID':<8} {'Skill':<20} {'Sent':<8} {'Group':<24} {'Pri':<4}  What happened")
    print("-" * 100)
    for r in rows:
        grp = r.get("group") or "(ungrouped)"
        pri = r.get("group_priority") or "—"
        what = r.get("what_happened", "")[:50]
        print(f"{r['feedback_id']:<8} {r.get('skill_name',''):<20} {r.get('sentiment',''):<8} {grp:<24} {pri:<4}  {what}")


def cmd_feedback_show(args):
    rows = read_feedback(args.workspace)
    row = next((r for r in rows if r["feedback_id"] == args.feedback_id), None)
    if not row:
        print(f"Error: {args.feedback_id} not found.", file=sys.stderr)
        sys.exit(1)
    for k, v in row.items():
        print(f"{k:22s}: {v}")


def cmd_feedback_set_group(args):
    rows = read_feedback(args.workspace)
    row = next((r for r in rows if r["feedback_id"] == args.feedback_id), None)
    if not row:
        print(f"Error: {args.feedback_id} not found.", file=sys.stderr)
        sys.exit(1)
    old = row.get("group") or "(none)"
    row["group"] = args.group
    write_feedback(args.workspace, rows)
    print(f"{args.feedback_id}: group '{old}' → '{args.group}'")


def cmd_feedback_set_priority(args):
    rows = read_feedback(args.workspace)
    updated = 0
    for row in rows:
        if row.get("group") == args.group:
            row["group_priority"] = str(args.priority)
            updated += 1
    if not updated:
        print(f"Warning: no rows with group='{args.group}'", file=sys.stderr)
        sys.exit(1)
    write_feedback(args.workspace, rows)
    print(f"Set group_priority={args.priority} on {updated} rows in group '{args.group}'")


def cmd_groups_summary(args):
    rows = read_feedback(args.workspace)
    grouped = [r for r in rows if r.get("group")]
    ungrouped_count = sum(1 for r in rows if not r.get("group"))

    groups: dict = {}
    for r in grouped:
        g = r["group"]
        if g not in groups:
            groups[g] = {
                "total": 0, "good": 0, "improve": 0,
                "priority": r.get("group_priority", ""),
                "skills": set(),
            }
        groups[g]["total"] += 1
        groups[g]["improve" if r["sentiment"] == "improve" else "good"] += 1
        if r.get("group_priority"):
            groups[g]["priority"] = r["group_priority"]
        if r.get("skill_name"):
            groups[g]["skills"].add(r["skill_name"])

    if not groups and not ungrouped_count:
        print("No feedback rows yet.")
        return

    print(f"Groups — {len(groups)} groups, {ungrouped_count} ungrouped\n")
    sorted_groups = sorted(
        groups.items(),
        key=lambda x: (-int(x[1]["priority"]) if x[1]["priority"] else 0, x[0]),
    )
    for gname, s in sorted_groups:
        pri = f"p{s['priority']}" if s["priority"] else "no priority"
        skills = ", ".join(sorted(s["skills"]))
        print(
            f"  {gname:<30}  {s['total']} rows  "
            f"({s['improve']} improve / {s['good']} good)  "
            f"{pri:<12}  [{skills}]"
        )

    if ungrouped_count:
        print(f"\n  {ungrouped_count} ungrouped — run 'feedback_list --ungrouped' to review")


def cmd_resolution_add(args):
    fb_rows = read_feedback(args.workspace)
    fb_ids = {r["feedback_id"] for r in fb_rows}
    ref_ids = args.feedback_ids.split()
    missing = [fid for fid in ref_ids if fid not in fb_ids]
    if missing:
        print(f"Error: feedback IDs not found: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    status = args.status
    if status == "addressed" and not args.what_changed:
        print("Error: --what-changed is required when --status addressed", file=sys.stderr)
        sys.exit(1)
    if status == "wont_fix" and not args.notes:
        print("Error: --notes is required when --status wont_fix (document the reason)", file=sys.stderr)
        sys.exit(1)

    res_rows = read_resolution(args.workspace)
    rid = _next_resolution_id(res_rows)
    row = {
        "resolution_id": rid,
        "feedback_ids": args.feedback_ids,
        "status": status,
        "what_changed": args.what_changed,
        "addressed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if status == "addressed" else "",
        "verified_by_session_id": "",
        "notes": args.notes,
    }
    res_rows.append(row)
    write_resolution(args.workspace, res_rows)
    print(f"Added {rid}: [{status}] addressing {args.feedback_ids}")


def cmd_resolution_verify(args):
    rows = read_resolution(args.workspace)
    row = next((r for r in rows if r["resolution_id"] == args.resolution_id), None)
    if not row:
        print(f"Error: {args.resolution_id} not found.", file=sys.stderr)
        sys.exit(1)
    if row["status"] != "addressed":
        print(
            f"Error: only 'addressed' resolutions can be verified "
            f"(current status: {row['status']})",
            file=sys.stderr,
        )
        sys.exit(1)
    row["verified_by_session_id"] = args.session_id
    write_resolution(args.workspace, rows)
    print(f"{args.resolution_id}: verified by session '{args.session_id}'")


def cmd_resolution_list(args):
    rows = read_resolution(args.workspace)
    if args.status:
        rows = [r for r in rows if r.get("status") == args.status]
    if not rows:
        print("No resolution rows match.")
        return
    print(f"{'ID':<8} {'Status':<12} {'Verified':<12}  Feedback IDs")
    print("-" * 70)
    for r in rows:
        verified = r.get("verified_by_session_id") or "—"
        print(f"{r['resolution_id']:<8} {r.get('status',''):<12} {verified:<12}  {r.get('feedback_ids','')}")
        if r.get("what_changed"):
            print(f"         {r['what_changed'][:80]}")


def cmd_resolution_show(args):
    rows = read_resolution(args.workspace)
    row = next((r for r in rows if r["resolution_id"] == args.resolution_id), None)
    if not row:
        print(f"Error: {args.resolution_id} not found.", file=sys.stderr)
        sys.exit(1)
    for k, v in row.items():
        print(f"{k:26s}: {v}")


# ── dispatch ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Skill Retro DB — CSV-based skill retrospective tracking"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # init
    p = subparsers.add_parser("init", help="Create feedback.csv and resolution.csv in workspace")
    p.add_argument("workspace")

    # feedback_add
    p = subparsers.add_parser("feedback_add", help="Append one feedback observation (Phase 1)")
    p.add_argument("workspace")
    p.add_argument("--skill", required=True, help="Skill name, e.g. deep-ideation")
    p.add_argument("--session-id", required=True, dest="session_id", help="Chat session ID")
    p.add_argument("--sentiment", required=True, choices=["good", "improve"])
    p.add_argument("--what-happened", required=True, dest="what_happened",
                   help="One sentence: the observed behavior")
    p.add_argument("--evidence", required=True,
                   help="Quote, line ref, file path, or row ID — required, not optional")

    # feedback_list
    p = subparsers.add_parser("feedback_list", help="List feedback rows (filterable)")
    p.add_argument("workspace")
    p.add_argument("--ungrouped", action="store_true", help="Show only rows where group is empty")
    p.add_argument("--skill", default="", help="Filter by skill name")
    p.add_argument("--sentiment", default="", choices=["", "good", "improve"])

    # feedback_show
    p = subparsers.add_parser("feedback_show", help="Show full detail for one feedback row")
    p.add_argument("workspace")
    p.add_argument("feedback_id")

    # feedback_set_group
    p = subparsers.add_parser("feedback_set_group",
                               help="Assign a group tag to a feedback row (Phase 2)")
    p.add_argument("workspace")
    p.add_argument("feedback_id")
    p.add_argument("group", help="Group tag, e.g. scorer-collapse")

    # feedback_set_priority
    p = subparsers.add_parser("feedback_set_priority",
                               help="Set group_priority on all rows in a group (Phase 3)")
    p.add_argument("workspace")
    p.add_argument("--group", required=True)
    p.add_argument("--priority", required=True, type=int, choices=range(1, 6), metavar="1-5",
                   help="1 = low, 5 = fix this first")

    # groups_summary
    p = subparsers.add_parser("groups_summary",
                               help="Summarize all groups: count, sentiment, priority (Phase 3)")
    p.add_argument("workspace")

    # resolution_add
    p = subparsers.add_parser("resolution_add",
                               help="Record a resolution after changing a skill (Phase 4)")
    p.add_argument("workspace")
    p.add_argument("--feedback-ids", required=True, dest="feedback_ids",
                   help="Space-separated feedback IDs this resolves: 'f001 f003'")
    p.add_argument("--what-changed", default="", dest="what_changed",
                   help="One to three sentences describing what changed in the skill. "
                        "Required when --status addressed.")
    p.add_argument("--status", default="open", choices=["open", "addressed", "wont_fix"])
    p.add_argument("--notes", default="",
                   help="Free text. Required when --status wont_fix — document the reason.")

    # resolution_verify
    p = subparsers.add_parser("resolution_verify",
                               help="Back-fill verified_by_session_id when a fix is confirmed")
    p.add_argument("workspace")
    p.add_argument("resolution_id")
    p.add_argument("--session-id", required=True, dest="session_id",
                   help="Session ID that confirmed the fix worked")

    # resolution_list
    p = subparsers.add_parser("resolution_list", help="List resolution rows")
    p.add_argument("workspace")
    p.add_argument("--status", default="", choices=["", "open", "addressed", "wont_fix"])

    # resolution_show
    p = subparsers.add_parser("resolution_show", help="Show full detail for one resolution row")
    p.add_argument("workspace")
    p.add_argument("resolution_id")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init": cmd_init,
        "feedback_add": cmd_feedback_add,
        "feedback_list": cmd_feedback_list,
        "feedback_show": cmd_feedback_show,
        "feedback_set_group": cmd_feedback_set_group,
        "feedback_set_priority": cmd_feedback_set_priority,
        "groups_summary": cmd_groups_summary,
        "resolution_add": cmd_resolution_add,
        "resolution_verify": cmd_resolution_verify,
        "resolution_list": cmd_resolution_list,
        "resolution_show": cmd_resolution_show,
    }

    if args.command == "init":
        commands[args.command](args)
    elif args.command in FEEDBACK_COMMANDS:
        shared = args.command in READ_ONLY_COMMANDS
        with locked_feedback(args.workspace, shared=shared):
            commands[args.command](args)
    elif args.command in RESOLUTION_COMMANDS:
        shared = args.command in READ_ONLY_COMMANDS
        with locked_resolution(args.workspace, shared=shared):
            commands[args.command](args)


if __name__ == "__main__":
    main()
