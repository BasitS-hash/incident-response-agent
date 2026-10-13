"""Tests for the audit log's hash chain — backend/audit/chain.py.

The point of the chain is that a row cannot be changed behind the log's back,
so most of these tests are written as the attacker: open ``audit.db`` directly,
edit it the way someone with filesystem access would, and assert that
verification notices and names the entry that first went wrong.

Two tests deliberately assert a *limitation* rather than a protection
(``test_a_forger_who_rebuilds_the_whole_chain_is_not_detected`` and
``test_truncating_the_tail_of_the_log_is_not_detected``). They are here so the
README's claim about what a local chain cannot do stays true as the code moves.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

import backend.audit.chain as chain
import backend.audit.log as audit_module


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the audit DB to a fresh temp file for every test."""
    monkeypatch.setattr(audit_module, "_DB_PATH", tmp_path / "test_audit.db")
    audit_module.init_db()


def _run_id() -> str:
    return str(uuid.uuid4())


@contextmanager
def _raw() -> Iterator[sqlite3.Connection]:
    """A connection that bypasses the audit module, i.e. what an attacker has.

    Every block below commits explicitly; this only guarantees the handle is
    closed, so the temp DB is not still open when the next test opens it.
    """
    conn = sqlite3.connect(str(audit_module._DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _entries() -> list[sqlite3.Row]:
    with _raw() as conn:
        return conn.execute("SELECT * FROM audit_chain ORDER BY seq").fetchall()


def _seed_two_runs() -> tuple[str, str]:
    """One approved run and one rejected run — the history a verifier walks."""
    first, second = _run_id(), _run_id()
    audit_module.record_run_started(first, "INC-101", {
        "severity": "P1",
        "affected_systems": ["auth-service", "redis"],
        "root_cause": "Connection pool reduced by deploy",
    })
    audit_module.record_run_completed(first, {
        "approved": True,
        "approver": "Alice Chen",
        "approval_notes": "LGTM",
        "email_sent": True,
    })
    audit_module.record_run_started(second, "INC-205", {"severity": "P2"})
    audit_module.record_run_completed(second, {
        "approved": False,
        "approver": "Bob",
        "approval_notes": "Need more info",
        "email_sent": False,
    })
    return first, second


# ── canonicalisation ──────────────────────────────────────────────────────

def test_canonical_bytes_ignores_key_insertion_order() -> None:
    """Two dicts with the same contents must hash the same, or verification
    would fail on rows nobody touched."""
    a = chain.canonical_bytes({"b": 2, "a": 1, "c": None})
    b = chain.canonical_bytes({"c": None, "a": 1, "b": 2})
    assert a == b


def test_canonical_bytes_distinguishes_null_from_missing() -> None:
    """``approver = NULL`` and "no approver column" are different facts."""
    assert chain.canonical_bytes({"approver": None}) != chain.canonical_bytes({})


def test_canonical_bytes_distinguishes_null_from_empty_string() -> None:
    assert chain.canonical_bytes({"notes": None}) != chain.canonical_bytes({"notes": ""})


def test_canonical_bytes_is_utf8_and_not_unicode_normalised() -> None:
    """Hashing a normalised form would let an attacker swap in an equivalent
    but differently-encoded string and still verify."""
    composed = chain.canonical_bytes({"approver": "René"})       # é
    decomposed = chain.canonical_bytes({"approver": "René"})    # e + combining acute
    assert composed != decomposed
    assert "René".encode() in composed


def test_canonical_bytes_rejects_floats() -> None:
    """No audit column is a float today. If one is added, the chain has to pick
    a representation deliberately rather than inherit repr()."""
    with pytest.raises(ValueError):
        chain.canonical_bytes({"duration": 1.5})


def test_canonical_bytes_rejects_unsupported_types() -> None:
    with pytest.raises(ValueError):
        chain.canonical_bytes({"when": object()})


def test_canonical_bytes_rejects_non_string_keys() -> None:
    """JSON has no integer keys; serialising one would be lossy."""
    with pytest.raises(ValueError):
        chain.canonical_bytes({1: "one"})


def test_canonical_bytes_handles_nested_lists() -> None:
    """No column holds a list today — ``affected_systems`` is stored as JSON
    text — but the digest input must stay well defined if one ever does."""
    assert chain.canonical_bytes({"systems": ["b", "a"]}) == b'{"systems":["b","a"]}'


# ── genesis ───────────────────────────────────────────────────────────────

def test_init_db_writes_a_genesis_entry() -> None:
    rows = _entries()
    assert len(rows) == 1
    assert rows[0]["kind"] == "genesis"
    assert rows[0]["seq"] == 1
    assert rows[0]["prev_hash"] == chain.GENESIS_PREV_HASH


def test_init_db_does_not_duplicate_genesis_across_restarts() -> None:
    """init_db runs on every API start; it must not append a second genesis."""
    audit_module.init_db()
    audit_module.init_db()
    kinds = [r["kind"] for r in _entries()]
    assert kinds.count("genesis") == 1


def test_verification_passes_on_an_empty_log() -> None:
    result = audit_module.verify_audit_chain()
    assert result.ok
    assert result.entries_checked == 1
    assert result.problems == ()


# ── a clean chain ─────────────────────────────────────────────────────────

def test_verification_passes_on_a_clean_chain() -> None:
    _seed_two_runs()
    result = audit_module.verify_audit_chain()
    assert result.ok, result.problems
    # genesis + 2 starts + 2 completions
    assert result.entries_checked == 5
    assert result.rows_checked == 2


def test_every_write_appends_exactly_one_entry() -> None:
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-101", {"severity": "P1"})
    assert [r["kind"] for r in _entries()] == ["genesis", "run_started"]
    audit_module.record_run_completed(rid, {"approved": True, "approver": "Alice"})
    assert [r["kind"] for r in _entries()] == ["genesis", "run_started", "run_completed"]


def test_completing_an_unknown_run_appends_nothing() -> None:
    """The UPDATE matches no row, so there is no row state to vouch for. An
    entry here would be a digest over nothing, and the chain would carry a
    claim about a run that never existed."""
    audit_module.record_run_completed("never-started", {
        "approved": True, "approver": "Alice",
    })
    assert [r["kind"] for r in _entries()] == ["genesis"]
    assert audit_module.verify_audit_chain().ok


def test_a_legitimate_write_after_verification_keeps_the_chain_valid() -> None:
    """The ordinary sequence: start a run, verify, approve it, verify again."""
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-101", {"severity": "P1"})
    assert audit_module.verify_audit_chain().ok

    audit_module.record_run_completed(rid, {
        "approved": True, "approver": "Alice Chen", "email_sent": True,
    })
    second = audit_module.verify_audit_chain()
    assert second.ok, second.problems
    assert second.entries_checked == 3


def test_verification_survives_a_restart() -> None:
    """A new process re-runs init_db against the existing file. Nothing about
    reopening the DB may look like tampering."""
    _seed_two_runs()
    before = audit_module.verify_audit_chain()
    audit_module.init_db()          # what the next API boot does
    after = audit_module.verify_audit_chain()
    assert before.ok and after.ok, after.problems
    assert after.entries_checked == before.entries_checked


def test_verification_tolerates_unicode_empty_strings_and_nulls() -> None:
    """A verifier that cries wolf on an ordinary ticket gets switched off."""
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-777", {
        "severity": "",
        "affected_systems": [],
        "triage_notes": "ログイン失敗 — 97 % cache miss 😤\ttabbed",
        "root_cause": None,
        "rca_summary": "",
        "recommended_fix": "René to roll back",
    })
    audit_module.record_run_completed(rid, {
        "approved": True,
        "approver": "René O'Neill-Smith",
        "approval_notes": "",
    })
    result = audit_module.verify_audit_chain()
    assert result.ok, result.problems


def test_a_column_added_after_a_row_was_chained_is_not_a_false_positive() -> None:
    """A future migration widens ``runs``. Entries written before it cannot
    cover the new column, and must not be reported as altered because of it."""
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-101", {"severity": "P1"})
    with _raw() as conn:
        conn.execute("ALTER TABLE runs ADD COLUMN reviewed_by TEXT")
        conn.execute("UPDATE runs SET reviewed_by = 'later-feature'")
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert result.ok, result.problems


# ── tampering with a run row ──────────────────────────────────────────────

def test_flipping_a_field_on_a_run_row_is_detected_and_the_row_named() -> None:
    """The row an attacker wants: who approved, and whether mail went out."""
    first, _second = _seed_two_runs()
    with _raw() as conn:
        conn.execute(
            "UPDATE runs SET approver = 'Someone Else' WHERE run_id = ?", (first,)
        )
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    problem = result.first_problem
    assert problem is not None
    assert problem.kind == "row_altered"
    assert problem.run_id == first
    assert "approver" in problem.detail


def test_clearing_the_email_sent_flag_is_detected() -> None:
    first, _ = _seed_two_runs()
    with _raw() as conn:
        conn.execute("UPDATE runs SET email_sent = 0 WHERE run_id = ?", (first,))
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "row_altered"
    assert "email_sent" in result.first_problem.detail


def test_deleting_a_run_row_is_detected() -> None:
    first, _ = _seed_two_runs()
    with _raw() as conn:
        conn.execute("DELETE FROM runs WHERE run_id = ?", (first,))
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "row_missing"
    assert result.first_problem.run_id == first


def test_inserting_a_run_row_that_no_entry_covers_is_detected() -> None:
    _seed_two_runs()
    with _raw() as conn:
        conn.execute(
            "INSERT INTO runs (run_id, incident_id, started_at, status) "
            "VALUES ('forged', 'INC-999', '2026-01-01T00:00:00+00:00', 'completed')"
        )
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "row_unchained"
    assert result.first_problem.run_id == "forged"


# ── tampering with the chain itself ───────────────────────────────────────

def test_editing_an_entry_payload_is_detected_at_that_entry() -> None:
    _seed_two_runs()
    target = _entries()[2]                        # the first run's completion
    payload = json.loads(target["payload"])
    payload["approver"] = "Someone Else"
    with _raw() as conn:
        conn.execute(
            "UPDATE audit_chain SET payload = ? WHERE seq = ?",
            (json.dumps(payload), target["seq"]),
        )
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "digest_mismatch"
    assert result.first_problem.seq == target["seq"]


def test_deleting_a_middle_entry_is_detected() -> None:
    _seed_two_runs()
    victim = _entries()[2]["seq"]
    with _raw() as conn:
        conn.execute("DELETE FROM audit_chain WHERE seq = ?", (victim,))
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.seq == victim
    assert result.first_problem.kind == "sequence_gap"


def test_reordering_two_entries_is_detected() -> None:
    """Swapping the seq numbers of two entries rewrites history's order. The
    seq is part of each digest, so the swap cannot survive."""
    _seed_two_runs()
    rows = _entries()
    a, b = rows[2]["seq"], rows[3]["seq"]
    with _raw() as conn:
        conn.execute("UPDATE audit_chain SET seq = -1 WHERE seq = ?", (a,))
        conn.execute("UPDATE audit_chain SET seq = ? WHERE seq = ?", (a, b))
        conn.execute("UPDATE audit_chain SET seq = ? WHERE seq = -1", (b,))
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.seq == a


def test_appending_a_forged_entry_without_a_valid_digest_is_detected() -> None:
    _seed_two_runs()
    last = _entries()[-1]
    with _raw() as conn:
        conn.execute(
            "INSERT INTO audit_chain "
            "(seq, recorded_at, kind, run_id, payload, prev_hash, entry_hash) "
            "VALUES (?, ?, 'run_completed', 'forged', '{}', ?, ?)",
            (
                last["seq"] + 1,
                "2026-01-01T00:00:00+00:00",
                last["entry_hash"],
                "0" * 64,
            ),
        )
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "digest_mismatch"
    assert result.first_problem.seq == last["seq"] + 1


def test_relinking_an_entry_to_the_wrong_predecessor_is_detected() -> None:
    """A forger who recomputes one entry's own digest but leaves prev_hash
    pointing at the wrong place breaks the link rather than the digest."""
    _seed_two_runs()
    rows = _entries()
    target = rows[3]
    forged_prev = rows[0]["entry_hash"]
    forged_hash = chain.entry_digest(
        seq=target["seq"],
        kind=target["kind"],
        recorded_at=target["recorded_at"],
        run_id=target["run_id"],
        prev_hash=forged_prev,
        payload=json.loads(target["payload"]),
    )
    with _raw() as conn:
        conn.execute(
            "UPDATE audit_chain SET prev_hash = ?, entry_hash = ? WHERE seq = ?",
            (forged_prev, forged_hash, target["seq"]),
        )
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "broken_link"
    assert result.first_problem.seq == target["seq"]


def test_an_unreadable_payload_is_reported_not_raised() -> None:
    _seed_two_runs()
    victim = _entries()[2]["seq"]
    with _raw() as conn:
        conn.execute(
            "UPDATE audit_chain SET payload = 'not json' WHERE seq = ?", (victim,)
        )
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "unreadable_payload"
    assert result.first_problem.seq == victim


def test_a_payload_that_is_not_an_object_is_reported() -> None:
    _seed_two_runs()
    victim = _entries()[2]["seq"]
    with _raw() as conn:
        conn.execute("UPDATE audit_chain SET payload = '[]' WHERE seq = ?", (victim,))
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "unreadable_payload"


def test_wiping_the_whole_chain_is_detected() -> None:
    """Deleting every entry leaves rows with nothing vouching for them; say so
    rather than returning a vacuously clean walk of zero entries."""
    _seed_two_runs()
    with _raw() as conn:
        conn.execute("DELETE FROM audit_chain")
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "missing_genesis"


def test_a_missing_genesis_entry_is_detected() -> None:
    _seed_two_runs()
    with _raw() as conn:
        conn.execute("DELETE FROM audit_chain WHERE seq = 1")
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "missing_genesis"


# ── the limits, asserted on purpose ───────────────────────────────────────

def test_a_forger_who_rebuilds_the_whole_chain_is_not_detected() -> None:
    """Stated plainly in the README: a local chain detects edits by someone who
    did not recompute it. Someone who can rewrite the file and redo every
    digest leaves nothing for this verifier to find — that needs an append-only
    store, an external witness, or a key the app cannot reach."""
    first, _ = _seed_two_runs()
    with _raw() as conn:
        conn.execute(
            "UPDATE runs SET approver = 'Someone Else' WHERE run_id = ?", (first,)
        )
        prev = chain.GENESIS_PREV_HASH
        for row in conn.execute("SELECT * FROM audit_chain ORDER BY seq").fetchall():
            payload = json.loads(row["payload"])
            if payload.get("run_id") == first and "approver" in payload:
                payload["approver"] = "Someone Else"
            digest = chain.entry_digest(
                seq=row["seq"],
                kind=row["kind"],
                recorded_at=row["recorded_at"],
                run_id=row["run_id"],
                prev_hash=prev,
                payload=payload,
            )
            conn.execute(
                "UPDATE audit_chain SET payload = ?, prev_hash = ?, entry_hash = ? "
                "WHERE seq = ?",
                (json.dumps(payload), prev, digest, row["seq"]),
            )
            prev = digest
        conn.commit()

    assert audit_module.verify_audit_chain().ok


def test_truncating_the_tail_of_the_log_is_not_detected() -> None:
    """Dropping the most recent entries together with their rows leaves a
    shorter but internally consistent chain. Nothing stored locally can say how
    long the log was supposed to be."""
    _first, second = _seed_two_runs()
    with _raw() as conn:
        conn.execute("DELETE FROM runs WHERE run_id = ?", (second,))
        conn.execute("DELETE FROM audit_chain WHERE run_id = ?", (second,))
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert result.ok
    assert result.entries_checked == 3


# ── migrating a DB whose rows predate the chain ───────────────────────────

def _legacy_db_with_rows(run_ids: list[str]) -> None:
    """Rebuild audit.db as it looked before the chain existed."""
    with _raw() as conn:
        conn.execute("DROP TABLE runs")
        conn.execute("DROP TABLE audit_chain")
        conn.execute(
            "CREATE TABLE runs ("
            "run_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, "
            "started_at TEXT NOT NULL, completed_at TEXT, "
            "status TEXT NOT NULL DEFAULT 'running', severity TEXT, "
            "affected_systems TEXT, triage_notes TEXT, root_cause TEXT, "
            "rca_summary TEXT, recommended_fix TEXT, approved INTEGER, "
            "approver TEXT, approval_notes TEXT, "
            "email_sent INTEGER NOT NULL DEFAULT 0)"
        )
        for i, rid in enumerate(run_ids):
            conn.execute(
                "INSERT INTO runs (run_id, incident_id, started_at, status, approver) "
                "VALUES (?, ?, ?, 'completed', 'Historic Approver')",
                (rid, f"INC-{100 + i}", f"2026-01-0{i + 1}T00:00:00+00:00"),
            )
        conn.commit()


def test_pre_existing_rows_are_adopted_at_migration_time() -> None:
    old = [_run_id(), _run_id()]
    _legacy_db_with_rows(old)

    audit_module.init_db()

    kinds = [r["kind"] for r in _entries()]
    assert kinds == ["genesis", "run_adopted", "run_adopted"]
    result = audit_module.verify_audit_chain()
    assert result.ok, result.problems
    assert result.adopted_runs == 2


def test_adopted_rows_are_covered_from_the_adoption_point_onward() -> None:
    """Adoption cannot authenticate what a row said before the chain existed,
    but it does pin what it said at migration time."""
    old = [_run_id()]
    _legacy_db_with_rows(old)
    audit_module.init_db()

    with _raw() as conn:
        conn.execute("UPDATE runs SET approver = 'Rewritten' WHERE run_id = ?", (old[0],))
        conn.commit()

    result = audit_module.verify_audit_chain()
    assert not result.ok
    assert result.first_problem is not None
    assert result.first_problem.kind == "row_altered"
    assert result.first_problem.run_id == old[0]


def test_adoption_happens_once_and_new_runs_chain_normally() -> None:
    old = [_run_id()]
    _legacy_db_with_rows(old)
    audit_module.init_db()
    audit_module.init_db()          # a second boot must not re-adopt

    rid = _run_id()
    audit_module.record_run_started(rid, "INC-500", {"severity": "P3"})
    audit_module.record_run_completed(rid, {"approved": True, "approver": "Alice"})

    kinds = [r["kind"] for r in _entries()]
    assert kinds == ["genesis", "run_adopted", "run_started", "run_completed"]
    assert audit_module.verify_audit_chain().ok


def test_migration_adds_the_chain_table_to_a_pre_existing_db() -> None:
    """The shape of the existing migration step: a deployed audit.db has no
    audit_chain table, and init_db has to add it without losing the rows."""
    old = [_run_id()]
    _legacy_db_with_rows(old)
    with _raw() as conn:
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
    assert "audit_chain" not in tables

    audit_module.init_db()

    assert audit_module.get_run(old[0]) is not None
    assert audit_module.verify_audit_chain().ok


# ── verification report ───────────────────────────────────────────────────

def test_report_lines_name_the_first_broken_entry() -> None:
    """The report is what a human reads at 3am, so it has to say where."""
    _seed_two_runs()
    victim = _entries()[2]["seq"]
    with _raw() as conn:
        conn.execute(
            "UPDATE audit_chain SET payload = '{}' WHERE seq = ?", (victim,)
        )
        conn.commit()

    text = audit_module.verify_audit_chain().report()
    assert "FAILED" in text
    assert f"entry {victim}" in text


def test_report_says_the_rest_of_the_chain_went_unchecked_when_it_broke() -> None:
    _seed_two_runs()
    with _raw() as conn:
        conn.execute("UPDATE audit_chain SET payload = '{}' WHERE seq = 3")
        conn.commit()

    text = audit_module.verify_audit_chain().report()
    assert "entries after 2 were not checked" in text


def test_report_does_not_claim_unchecked_entries_when_the_chain_is_intact() -> None:
    """An edited ``runs`` row is caught in the second pass — the chain itself
    walked to the end. Claiming entries went unchecked would send the reader to
    the wrong file."""
    first, _ = _seed_two_runs()
    with _raw() as conn:
        conn.execute("UPDATE runs SET approver = 'Someone Else' WHERE run_id = ?", (first,))
        conn.commit()

    text = audit_module.verify_audit_chain().report()
    assert "row_altered" in text
    assert "not checked" not in text


def test_report_lines_on_a_clean_chain_say_so() -> None:
    _seed_two_runs()
    text = audit_module.verify_audit_chain().report()
    assert "verified" in text
    assert "5 entries" in text


# ── CLI ───────────────────────────────────────────────────────────────────

def test_cli_exits_zero_and_prints_the_count_on_a_clean_chain(capsys) -> None:
    from backend.audit import verify as verify_cli

    _seed_two_runs()
    code = verify_cli.main(["--db", str(audit_module._DB_PATH)])
    assert code == 0
    assert "5 entries" in capsys.readouterr().out


def test_cli_exits_nonzero_and_names_the_entry_when_tampered(capsys) -> None:
    from backend.audit import verify as verify_cli

    _seed_two_runs()
    victim = _entries()[2]["seq"]
    with _raw() as conn:
        conn.execute("UPDATE audit_chain SET payload = '{}' WHERE seq = ?", (victim,))
        conn.commit()

    code = verify_cli.main(["--db", str(audit_module._DB_PATH)])
    assert code == 1
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert f"entry {victim}" in out


def test_cli_verifies_a_copy_of_the_db_without_touching_the_original(tmp_path) -> None:
    """The useful forensic move: verify a copy, with the app shut down. The CLI
    must not need the module's own DB path to do it."""
    import shutil

    from backend.audit import verify as verify_cli

    _seed_two_runs()
    copy = tmp_path / "copy.db"
    shutil.copy(audit_module._DB_PATH, copy)

    assert verify_cli.main(["--db", str(copy)]) == 0


def test_cli_reports_a_missing_db_rather_than_crashing(tmp_path, capsys) -> None:
    from backend.audit import verify as verify_cli

    code = verify_cli.main(["--db", str(tmp_path / "nope.db")])
    assert code == 2
    assert "not found" in capsys.readouterr().out


def test_cli_reports_an_unreadable_db_rather_than_claiming_it_is_fine(
    tmp_path, capsys
) -> None:
    """Exit 2, not 0: a cron job must not read "could not open it" as "clean"."""
    from backend.audit import verify as verify_cli

    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not a database")

    code = verify_cli.main(["--db", str(junk)])
    assert code == 2
    assert "could not be read" in capsys.readouterr().out
