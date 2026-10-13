"""Check the audit log's hash chain from the command line.

    python -m backend.audit.verify
    python -m backend.audit.verify --db /tmp/audit-copy.db

There is an HTTP endpoint for this too (``GET /audit/verify``), and it is the
convenient one — but it is answered by the same process that writes the log, so
it is not the one to trust if you have a reason to doubt the log. This runs with
the API stopped, without the API key, and with ``--db`` against a copy of the
file taken out of the way of whatever is being investigated.

Exit status: 0 verified, 1 tampering found, 2 the log could not be read. The
distinction matters for a cron job — "could not read it" must not be reported as
"it is fine".
"""
from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from backend.audit import log


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.audit.verify",
        description="Verify the incident audit log's hash chain.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="audit database to check (default: backend/data/audit.db)",
    )
    args = parser.parse_args(argv)

    db_path = args.db or log._DB_PATH
    if not db_path.exists():
        print(f"audit log not found: {db_path}")
        return 2

    try:
        result = log.verify_audit_chain(db_path)
    except sqlite3.Error as exc:
        print(f"audit log could not be read: {exc}")
        return 2

    print(result.report())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
