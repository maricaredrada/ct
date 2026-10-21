from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.attendance import record_scan


def _insert_user(conn, admin_id, fingerprint_id=101):
    user_id = str(uuid.uuid4())
    with conn:
        conn.execute(
            'INSERT INTO "USER" (UserID, AdminID, Name, FingerprintID, Classification, Status) VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, admin_id, "Alice", fingerprint_id, "Writer", "active"),
        )
    return user_id


def test_time_in_then_time_out(db_conn):
    conn, admin_id = db_conn
    user_id = _insert_user(conn, admin_id)

    first = record_scan(conn, user_id, debounce_seconds=0)
    assert first.action == "time_in"

    with conn:
        conn.execute(
            "UPDATE ATTENDANCE_LOG SET TimeIn = ? WHERE LogID = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=45)).replace(microsecond=0).isoformat(), first.log_id),
        )

    second = record_scan(conn, user_id, debounce_seconds=0)
    assert second.action == "time_out"

    row = conn.execute("SELECT TimeOut, Duration FROM ATTENDANCE_LOG WHERE LogID = ?", (first.log_id,)).fetchone()
    assert row["TimeOut"] is not None
    assert row["Duration"] >= 1


def test_debounce_prevents_immediate_duplicate(db_conn):
    conn, admin_id = db_conn
    user_id = _insert_user(conn, admin_id, fingerprint_id=102)

    first = record_scan(conn, user_id, debounce_seconds=120)
    assert first.action == "time_in"

    duplicate = record_scan(conn, user_id, debounce_seconds=120)
    assert duplicate.duplicate is True
