from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)


class FirebaseConfigError(RuntimeError):
    pass


@dataclass
class SyncSummary:
    members_synced: int = 0
    attendance_synced: int = 0
    failures: int = 0


class FirestoreClientProtocol:
    def set_document(self, collection: str, doc_id: str, payload: dict[str, Any]) -> None:  # pragma: no cover - protocol
        raise NotImplementedError


class FirestoreSyncService:
    def __init__(self, conn: sqlite3.Connection, firestore_client: FirestoreClientProtocol | None) -> None:
        self.conn = conn
        self.firestore_client = firestore_client

    def sync(self) -> SyncSummary:
        if self.firestore_client is None:
            raise FirebaseConfigError(
                "Firebase Admin SDK is not configured. Set FIREBASE_CREDENTIALS_FILE and FIREBASE_PROJECT_ID."
            )

        summary = SyncSummary()
        members_synced, member_failures = self._sync_members()
        summary.members_synced += members_synced
        summary.failures += member_failures
        synced, failures = self._sync_attendance()
        summary.attendance_synced += synced
        summary.failures += failures
        return summary

    def _sync_members(self) -> tuple[int, int]:
        rows = self.conn.execute(
            """
            SELECT UserID, AdminID, Name, FingerprintID, Classification, Status, EnrollmentStatus
            FROM "USER"
            """
        ).fetchall()
        count = 0
        failures = 0
        for row in rows:
            payload = dict(row)
            try:
                self.firestore_client.set_document("members", row["UserID"], payload)
                count += 1
            except Exception:
                LOGGER.exception("Failed to sync member %s", row["UserID"])
                failures += 1
        return count, failures

    def _sync_attendance(self) -> tuple[int, int]:
        rows = self.conn.execute(
            """
            SELECT LogID, UserID, Date, TimeIn, TimeOut, Duration, SyncStatus
            FROM ATTENDANCE_LOG
            WHERE SyncStatus IN ('pending', 'failed')
            ORDER BY TimeIn ASC
            """
        ).fetchall()

        synced = 0
        failures = 0
        for row in rows:
            log_id = row["LogID"]
            try:
                self.firestore_client.set_document("attendance", log_id, dict(row))
                self.conn.execute(
                    "UPDATE ATTENDANCE_LOG SET SyncStatus = 'synced' WHERE LogID = ?",
                    (log_id,),
                )
                synced += 1
            except Exception:
                LOGGER.exception("Failed to sync attendance log %s", log_id)
                self.conn.execute(
                    "UPDATE ATTENDANCE_LOG SET SyncStatus = 'failed' WHERE LogID = ?",
                    (log_id,),
                )
                failures += 1
        self.conn.commit()
        return synced, failures


class InMemoryFirestoreClient(FirestoreClientProtocol):
    def __init__(self) -> None:
        self.storage: dict[str, dict[str, dict[str, Any]]] = {}

    def set_document(self, collection: str, doc_id: str, payload: dict[str, Any]) -> None:
        self.storage.setdefault(collection, {})[doc_id] = payload


class FirebaseAdminFirestoreClient(FirestoreClientProtocol):
    def __init__(self, firestore_db) -> None:
        self.firestore_db = firestore_db

    def set_document(self, collection: str, doc_id: str, payload: dict[str, Any]) -> None:
        self.firestore_db.collection(collection).document(doc_id).set(payload, merge=True)
