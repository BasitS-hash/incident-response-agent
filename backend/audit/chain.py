"""Tamper evidence for the audit log.

``log.py`` writes rows to SQLite. Anyone with filesystem access to
``backend/data/audit.db`` — or any bug in this application — can UPDATE a row,
DELETE one, or renumber history, and a plain table reveals none of it. For an
approval gate the row an attacker most wants is exactly the one that matters:
who approved, and whether a notification went out.

So every write also appends an entry to ``audit_chain``: a snapshot of the row
as it stands after the write, hashed together with its position and with the
previous entry's digest. Changing or removing anything breaks the digests from
that point on, and :func:`verify_chain` walks the log and names the first entry
that does not hold up.

**What this proves, and what it does not.** A local hash chain detects tampering
by someone who edited the file and did not bother to recompute the chain — a
stray UPDATE, a bug, a careless hand. It does **not** stop someone who can
rewrite the whole database and redo every digest from genesis, because the chain
is anchored to nothing outside the file. It also cannot notice entries removed
from the *end* of the log: dropping the most recent entries along with their
rows leaves a shorter chain that is internally consistent, and nothing stored
locally says how long the log was supposed to be. Closing either gap needs
something this process does not have — an append-only store, an external
witness, or a signing key the application cannot reach. Two tests in
``tests/test_audit_chain.py`` assert both limits on purpose, so this paragraph
stays true.

Rows already in a deployed ``audit.db`` predate the chain. They are *adopted* at
migration time (kind ``run_adopted``): what they said at adoption is pinned from
then on, but what they said before it cannot be established by anything here.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

# Part of every digest. Changing the hashed form means changing this, which
# invalidates existing chains by design rather than by accident.
CHAIN_FORMAT = "ira-audit-chain-v1"

# Genesis has no predecessor. A zeroed digest rather than an empty string keeps
# every prev_hash the same shape, so the walk below needs no special case.
GENESIS_PREV_HASH = "0" * 64

# ``seq INTEGER PRIMARY KEY`` is deliberately the rowid alias: SQLite may
# renumber an *implicit* rowid during VACUUM, and a renumbered seq would read as
# reordered history. Declared this way, the numbers are ours and they are stable.
_CREATE_CHAIN = """
    CREATE TABLE IF NOT EXISTS audit_chain (
        seq         INTEGER PRIMARY KEY,
        recorded_at TEXT NOT NULL,
        kind        TEXT NOT NULL,
        run_id      TEXT,
        payload     TEXT NOT NULL,
        prev_hash   TEXT NOT NULL,
        entry_hash  TEXT NOT NULL
    )
"""


# ── canonicalisation ──────────────────────────────────────────────────────

def canonical_bytes(payload: Mapping[str, object]) -> bytes:
    """Serialise a payload deterministically, for hashing.

    Verification recomputes a digest from a row read back out of SQLite weeks
    later, possibly under a different Python, so the serialisation has to be
    pinned rather than incidental. This is the part that decides whether the
    verifier is useful: if it is sloppy, verification fails on rows nobody
    touched, and a verifier that cries wolf gets switched off.

    * **Key order** is sorted. ``dict`` order is insertion order, and a row's
      column order is not guaranteed stable across a migration.
    * **``None`` is kept**, encoded as ``null``. A NULL column and an absent
      column are different facts and must not hash alike.
    * **No whitespace** between tokens, so a pretty-printer cannot change a
      digest.
    * **UTF-8, not unicode-normalised.** The digest covers the bytes the ticket
      actually carried; normalising here would let someone swap ``é`` for
      ``e``+U+0301 and still verify.
    * **Floats are rejected.** No audit column is a float. Inheriting
      ``repr()`` for one added later would make the digest depend on the
      runtime's float formatting, which is how a chain starts failing on
      untouched rows after an upgrade.
    """
    return json.dumps(
        _canonical_value(dict(payload)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_value(value: object) -> object:
    """Pass through the types a row column can hold, reject the rest loudly."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Mapping):
        return {_canonical_key(k): _canonical_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(v) for v in value]
    raise ValueError(f"not canonicalisable: {type(value).__name__}")


def _canonical_key(key: object) -> str:
    if not isinstance(key, str):
        raise ValueError(f"payload keys must be strings, got {type(key).__name__}")
    return key


def entry_digest(
    *,
    seq: int,
    kind: str,
    recorded_at: str,
    run_id: str | None,
    prev_hash: str,
    payload: Mapping[str, object],
) -> str:
    """Hash one entry over its own content plus its predecessor's digest.

    ``seq`` is inside the digest as well as implied by the linkage, so
    renumbering two entries to reorder history breaks them both. Everything
    goes into one JSON document rather than being concatenated, so no field's
    content can be arranged to look like a field boundary.
    """
    return hashlib.sha256(
        canonical_bytes({
            "v": CHAIN_FORMAT,
            "seq": seq,
            "kind": kind,
            "recorded_at": recorded_at,
            "run_id": run_id,
            "prev": prev_hash,
            "payload": payload,
        })
    ).hexdigest()


# ── writing ───────────────────────────────────────────────────────────────

def ensure_chain(conn: sqlite3.Connection) -> None:
    """Create the chain table, and start the chain if it is not started yet.

    Called from ``init_db``, so it runs on every API boot and must be
    idempotent. On a database that already holds runs, those rows are adopted
    here: one ``run_adopted`` entry each, in a deterministic order, pinning what
    each row said at migration time. Adoption is honest about its own limit —
    the entry kind says these rows were not chained when they were written.
    """
    conn.execute(_CREATE_CHAIN)
    if _head(conn) is not None:
        return

    append_entry(conn, kind="genesis", run_id=None, payload={})
    pre_existing = conn.execute(
        "SELECT * FROM runs ORDER BY started_at, run_id"
    ).fetchall()
    for row in pre_existing:
        append_entry(
            conn, kind="run_adopted", run_id=row["run_id"], payload=dict(row)
        )


def append_entry(
    conn: sqlite3.Connection,
    *,
    kind: str,
    run_id: str | None,
    payload: Mapping[str, object],
) -> None:
    """Append one entry, chained to whatever is at the head of the log.

    Call this inside the same transaction as the row write it records, and
    *after* that write: the INSERT or UPDATE has already taken SQLite's write
    lock by then, so no second writer can commit an entry between this read of
    the head and this append. Done the other way round there is a window where
    two processes chain from the same predecessor and the log reads as tampered
    with — a false alarm produced by the log's own writer.
    """
    recorded_at = datetime.now(UTC).isoformat()
    head = _head(conn)
    seq = 1 if head is None else int(head["seq"]) + 1
    prev_hash = GENESIS_PREV_HASH if head is None else head["entry_hash"]
    conn.execute(
        """
        INSERT INTO audit_chain (
            seq, recorded_at, kind, run_id, payload, prev_hash, entry_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            seq,
            recorded_at,
            kind,
            run_id,
            canonical_bytes(payload).decode("utf-8"),
            prev_hash,
            entry_digest(
                seq=seq,
                kind=kind,
                recorded_at=recorded_at,
                run_id=run_id,
                prev_hash=prev_hash,
                payload=payload,
            ),
        ),
    )


def _head(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT seq, entry_hash FROM audit_chain ORDER BY seq DESC LIMIT 1"
    ).fetchone()


# ── verification ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChainProblem:
    """One thing that does not hold up, located well enough to go look at it."""

    kind: str
    detail: str
    seq: int | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ChainVerification:
    entries_checked: int = 0
    rows_checked: int = 0
    adopted_runs: int = 0
    problems: tuple[ChainProblem, ...] = ()
    # Set only when the walk over the chain stopped early. A row that was
    # altered without the chain being touched is a different kind of finding:
    # the chain is intact there, and saying otherwise sends the reader to the
    # wrong place.
    chain_broken_at: int | None = None

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def first_problem(self) -> ChainProblem | None:
        """The one to act on: everything after a broken link is unverifiable."""
        return self.problems[0] if self.problems else None

    def report(self) -> str:
        """The text a human reads. Says where, not just whether."""
        if self.ok:
            return (
                f"audit chain verified: {self.entries_checked} entries, "
                f"{self.rows_checked} run row{_s(self.rows_checked)}, "
                f"{self.adopted_runs} adopted from before the chain existed"
            )
        lines = [
            f"audit chain verification FAILED after {self.entries_checked} "
            f"entries checked:"
        ]
        lines += [f"  {_where(p)}: {p.kind} — {p.detail}" for p in self.problems]
        if self.chain_broken_at is not None:
            lines.append(
                f"  entries after {self.chain_broken_at} were not checked — a "
                f"chain cannot vouch for anything past its first break"
            )
        return "\n".join(lines)


def _s(count: int) -> str:
    return "" if count == 1 else "s"


def _where(problem: ChainProblem) -> str:
    where = "chain" if problem.seq is None else f"entry {problem.seq}"
    if problem.run_id:
        where += f" (run {problem.run_id})"
    return where


def verify_chain(conn: sqlite3.Connection) -> ChainVerification:
    """Walk the log and report the first entry that does not hold up.

    Two passes, in this order and for a reason:

    1. the chain itself — digests, links, numbering. This stops at the first
       break, because nothing after it can be judged.
    2. the ``runs`` table against the chain. Someone who edits a row without
       touching ``audit_chain`` leaves pass 1 clean, so the live row is compared
       against the snapshot the chain recorded for it. Only the columns in that
       snapshot are compared: a column added by a later migration cannot be
       covered by an entry written before it existed, and reporting it as an
       alteration would be exactly the false alarm this has to avoid.
    """
    entries = conn.execute("SELECT * FROM audit_chain ORDER BY seq").fetchall()
    if not entries:
        return ChainVerification(problems=(ChainProblem(
            kind="missing_genesis",
            detail="the log is empty — not even the genesis entry remains",
        ),), chain_broken_at=0)
    if entries[0]["seq"] != 1 or entries[0]["kind"] != "genesis":
        return ChainVerification(problems=(ChainProblem(
            kind="missing_genesis",
            seq=int(entries[0]["seq"]),
            detail="the log does not start at its genesis entry — entries were "
                   "removed from the front",
        ),), chain_broken_at=0)

    problems: list[ChainProblem] = []
    # run_id -> (seq, snapshot) for the most recent entry covering that run.
    covered: dict[str, tuple[int, dict]] = {}
    adopted = 0
    checked = 0
    prev_hash = GENESIS_PREV_HASH
    expected_seq = 1

    for row in entries:
        seq = int(row["seq"])
        if seq != expected_seq:
            problems.append(ChainProblem(
                kind="sequence_gap",
                seq=expected_seq,
                detail=f"expected entry {expected_seq}, found {seq} — an entry "
                       f"was removed or renumbered",
            ))
            break

        try:
            payload = json.loads(row["payload"])
            if not isinstance(payload, dict):
                raise ValueError("payload is not a JSON object")
        except Exception as exc:
            problems.append(ChainProblem(
                kind="unreadable_payload",
                seq=seq,
                run_id=row["run_id"],
                detail=f"payload will not parse: {exc}",
            ))
            break

        if row["prev_hash"] != prev_hash:
            problems.append(ChainProblem(
                kind="broken_link",
                seq=seq,
                run_id=row["run_id"],
                detail=f"links to {row['prev_hash'][:12]}…, but entry "
                       f"{seq - 1} hashes to {prev_hash[:12]}…",
            ))
            break

        digest = entry_digest(
            seq=seq,
            kind=row["kind"],
            recorded_at=row["recorded_at"],
            run_id=row["run_id"],
            prev_hash=row["prev_hash"],
            payload=payload,
        )
        if digest != row["entry_hash"]:
            problems.append(ChainProblem(
                kind="digest_mismatch",
                seq=seq,
                run_id=row["run_id"],
                detail="recomputed digest does not match the stored one — this "
                       "entry's recorded content was changed",
            ))
            break

        if row["kind"] == "run_adopted":
            adopted += 1
        if row["run_id"] is not None:
            covered[row["run_id"]] = (seq, payload)
        prev_hash = row["entry_hash"]
        expected_seq += 1
        checked += 1

    if problems:
        return ChainVerification(
            entries_checked=checked,
            adopted_runs=adopted,
            problems=tuple(problems),
            chain_broken_at=checked,
        )

    live = {
        row["run_id"]: dict(row)
        for row in conn.execute("SELECT * FROM runs").fetchall()
    }
    for run_id, (seq, snapshot) in covered.items():
        row = live.get(run_id)
        if row is None:
            problems.append(ChainProblem(
                kind="row_missing",
                seq=seq,
                run_id=run_id,
                detail="the chain records this run but no row is left in `runs`",
            ))
            continue
        changed = sorted(
            key for key, value in snapshot.items()
            if key not in row or row[key] != value
        )
        if changed:
            problems.append(ChainProblem(
                kind="row_altered",
                seq=seq,
                run_id=run_id,
                detail="changed since it was recorded: " + ", ".join(changed),
            ))
    for run_id in live:
        if run_id not in covered:
            problems.append(ChainProblem(
                kind="row_unchained",
                run_id=run_id,
                detail="a row no chain entry covers — it was written to the "
                       "database outside the audit log",
            ))

    return ChainVerification(
        entries_checked=checked,
        rows_checked=len(live),
        adopted_runs=adopted,
        problems=tuple(problems),
    )
