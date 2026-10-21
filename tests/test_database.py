from __future__ import annotations

import uuid

import pytest


def test_schema_has_required_tables(db_conn):
    conn, _ = db_conn
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('ADMINISTRATOR', 'USER', 'ATTENDANCE_LOG')"
        ).fetchall()
    }
    assert tables == {"ADMINISTRATOR", "USER", "ATTENDANCE_LOG"}


def test_classification_constraint(db_conn):
    conn, admin_id = db_conn
    with pytest.raises(Exception):
        with conn:
            conn.execute(
                'INSERT INTO "USER" (UserID, AdminID, Name, FingerprintID, Classification, Status) VALUES (?, ?, ?, ?, ?, ?)',
                (str(uuid.uuid4()), admin_id, "Invalid", 1, "Editor", "active"),
            )
