#!/usr/bin/env python3
"""Sylar ledger: the searchable index of every capability absorbed into your agent.

Usage:
  ledger.py add --source URL --author HANDLE --power TYPE --name NAME \
                --mechanism "one line" --home PATH --proof PATH|unproven \
                [--project NAME] [--note TEXT] [--json]
  ledger.py check "<url or name or mechanism words>" [--json]
  ledger.py list [--power TYPE] [--project NAME] [--limit N] [--json]
  ledger.py search "<terms>" [--json]

Ledger file: $SYLAR_LEDGER (default ~/.sylar/ledger.jsonl). One JSON
object per line, append-only, newest last. Timestamps are taken from the
system clock in IST at write time, never supplied by hand.

Exit codes: 0 success | 1 failure | 2 bad invocation | 3 (check only) match found
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

POWERS = ("prompt", "technique", "workflow", "tool", "config", "knowledge", "voice")
LEDGER = Path(os.environ.get("SYLAR_LEDGER", Path.home() / ".sylar/ledger.jsonl"))


def now_ist() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M IST")


def load() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for n, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"warning: skipping malformed line {n}", file=sys.stderr)
    return rows


def norm_url(u: str) -> str:
    u = u.strip().lower().rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u)
    u = u.replace("twitter.com/", "x.com/")
    return u.split("?")[0]


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", s.lower()) if w not in STOP}


STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "then", "than",
        "are", "was", "use", "using", "via", "one", "any", "all", "not", "but"}


def matches(rows: list[dict], query: str) -> list[tuple[dict, str]]:
    q_url = norm_url(query)
    q_words = words(query)
    out = []
    for r in rows:
        if q_url and norm_url(r.get("source", "")) == q_url:
            out.append((r, "same source url"))
            continue
        if query.strip().lower() == r.get("name", "").lower():
            out.append((r, "same name"))
            continue
        hay = words(" ".join([r.get("name", ""), r.get("mechanism", ""), r.get("note", "")]))
        overlap = q_words & hay
        if q_words and len(overlap) >= max(2, int(0.6 * len(q_words))):
            out.append((r, "mechanism overlap: " + " ".join(sorted(overlap))))
    return out


def fmt(r: dict) -> str:
    return (f"{r['ts']}  [{r['power']}] {r['name']}  <- @{r.get('author','?')}  "
            f"home={r['home']}  proof={r['proof']}  project={r.get('project','general')}")


def cmd_add(a) -> int:
    if a.power not in POWERS:
        print(f"error: --power must be one of {', '.join(POWERS)}", file=sys.stderr)
        return 2
    for f in ("source", "author", "name", "mechanism", "home", "proof"):
        if not getattr(a, f).strip():
            print(f"error: --{f} is required and must not be blank", file=sys.stderr)
            return 2
    row = {
        "ts": now_ist(),
        "source": a.source.strip(),
        "author": a.author.strip().lstrip("@"),
        "power": a.power,
        "name": a.name.strip(),
        "mechanism": a.mechanism.strip(),
        "home": a.home.strip(),
        "proof": a.proof.strip(),
        "project": (a.project or "general").strip(),
        "status": "unproven" if a.proof.strip().lower() == "unproven" else "absorbed",
    }
    if a.note:
        row["note"] = a.note.strip()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False, indent=2) if a.json else "added: " + fmt(row))
    return 0


def cmd_check(a) -> int:
    hits = matches(load(), a.query)
    if a.json:
        print(json.dumps([{"why": why, **r} for r, why in hits], ensure_ascii=False, indent=2))
    elif hits:
        for r, why in hits:
            print(f"EXISTS ({why}): {fmt(r)}")
    else:
        print("no match: not yet absorbed")
    return 3 if hits else 0


def cmd_list(a) -> int:
    rows = load()
    if a.power:
        rows = [r for r in rows if r.get("power") == a.power]
    if a.project:
        rows = [r for r in rows if r.get("project") == a.project]
    rows = rows[-a.limit:] if a.limit else rows
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in reversed(rows):
            print(fmt(r))
        print(f"{len(rows)} absorbed power(s) shown, newest first", file=sys.stderr)
    return 0


def cmd_search(a) -> int:
    q = words(a.terms)
    rows = [r for r in load() if q & words(json.dumps(r, ensure_ascii=False))]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in reversed(rows):
            print(fmt(r))
        if not rows:
            print("no results", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="append one absorbed power")
    for f in ("source", "author", "name", "mechanism", "home", "proof"):
        p.add_argument(f"--{f}", required=True)
    p.add_argument("--power", required=True, choices=POWERS)
    p.add_argument("--project", default="general")
    p.add_argument("--note", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("check", help="exit 3 if url/name/mechanism already absorbed")
    p.add_argument("query")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("list", help="newest first")
    p.add_argument("--power", choices=POWERS)
    p.add_argument("--project")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("search", help="word search across all fields")
    p.add_argument("terms")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_search)

    a = ap.parse_args()
    try:
        return a.fn(a)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
