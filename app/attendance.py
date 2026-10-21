from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class AttendanceResult:
    action: str
    log_id: str | None
    duplicate: bool = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def record_scan(conn: sqlite3.Connection, user_id: str, debounce_seconds: int) -> AttendanceResult:
    now = _utc_now()
    now_iso = _to_iso(now)

    conn.execute("BEGIN IMMEDIATE")
    try:
        latest = conn.execute(
            """
            SELECT LogID, TimeIn, TimeOut
            FROM ATTENDANCE_LOG
            WHERE UserID = ?
            ORDER BY COALESCE(TimeOut, TimeIn) DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

        if latest:
            last_ts = latest["TimeOut"] or latest["TimeIn"]
            if last_ts:
                last_dt = datetime.fromisoformat(last_ts)
                elapsed = (now - last_dt).total_seconds()
                if elapsed < debounce_seconds:
                    conn.rollback()
                    return AttendanceResult(action="debounced", log_id=None, duplicate=True)

        open_row = conn.execute(
            """
            SELECT LogID, TimeIn FROM ATTENDANCE_LOG
            WHERE UserID = ? AND TimeOut IS NULL
            ORDER BY TimeIn DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

        if open_row:
            log_id = open_row["LogID"]
            time_in = datetime.fromisoformat(open_row["TimeIn"])
            duration_seconds = int((now - time_in).total_seconds())
            conn.execute(
                """
                UPDATE ATTENDANCE_LOG
                SET TimeOut = ?, Duration = ?, SyncStatus = 'pending'
                WHERE LogID = ?
                """,
                (now_iso, duration_seconds, log_id),
            )
            conn.commit()
            return AttendanceResult(action="time_out", log_id=log_id)

        log_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO ATTENDANCE_LOG (LogID, UserID, Date, TimeIn, SyncStatus)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (log_id, user_id, now.date().isoformat(), now_iso),
        )
        conn.commit()
        return AttendanceResult(action="time_in", log_id=log_id)
    except Exception:
        conn.rollback()
        raise
