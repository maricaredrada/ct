from __future__ import annotations

import uuid

import pytest

from app.firebase_sync import FirestoreSyncService, InMemoryFirestoreClient


def _seed(conn, admin_id):
    user_id = str(uuid.uuid4())
    log_id = str(uuid.uuid4())
    with conn:
        conn.execute(
            'INSERT INTO "USER" (UserID, AdminID, Name, FingerprintID, Classification, Status) VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, admin_id, "Bob", 200, "Cartoonist", "active"),
        )
        conn.execute(
            "INSERT INTO ATTENDANCE_LOG (LogID, UserID, Date, TimeIn, SyncStatus) VALUES (?, ?, date('now'), datetime('now'), 'pending')",
            (log_id, user_id),
        )
    return user_id, log_id


def test_sync_idempotent_with_stable_ids(db_conn):
    conn, admin_id = db_conn
    _, log_id = _seed(conn, admin_id)
    client = InMemoryFirestoreClient()

    service = FirestoreSyncService(conn, client)
    first = service.sync()
    second = service.sync()

    assert first.attendance_synced == 1
    assert second.attendance_synced == 0
    assert client.storage["attendance"][log_id]["LogID"] == log_id


def test_offline_persistence_keeps_pending(db_conn):
    conn, admin_id = db_conn
    _, log_id = _seed(conn, admin_id)

    class FailingClient:
        def set_document(self, collection, doc_id, payload):
            raise RuntimeError("offline")

    service = FirestoreSyncService(conn, FailingClient())
    result = service.sync()

    assert result.failures == 2
    row = conn.execute("SELECT SyncStatus FROM ATTENDANCE_LOG WHERE LogID = ?", (log_id,)).fetchone()
    assert row["SyncStatus"] == "failed"
