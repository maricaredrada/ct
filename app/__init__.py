from __future__ import annotations

import logging
import sqlite3
import uuid

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for

from .attendance import record_scan
from .auth import AuthError, admin_required, verify_admin_token
from .config import Config
from .constants import CLASSIFICATIONS, USER_STATUSES
from .db import connect_db, init_db
from .firebase_sync import FirebaseAdminFirestoreClient, FirebaseConfigError, FirestoreSyncService
from .hardware import (
    AS608Config,
    AS608SerialFingerprintSensor,
    GPIOConfig,
    MockFeedbackController,
    MockFingerprintSensor,
    RaspberryPiFeedbackController,
)

LOGGER = logging.getLogger(__name__)


def _build_firebase_verifier(config: Config):
    if not config.FIREBASE_CREDENTIALS_FILE or not config.FIREBASE_PROJECT_ID:
        return None

    import firebase_admin  # type: ignore
    from firebase_admin import auth, credentials  # type: ignore

    if not firebase_admin._apps:
        cred = credentials.Certificate(config.FIREBASE_CREDENTIALS_FILE)
        firebase_admin.initialize_app(cred, {"projectId": config.FIREBASE_PROJECT_ID})

    def _verify(id_token: str):
        return auth.verify_id_token(id_token)

    return _verify


def _build_firestore_client(config: Config):
    if not config.FIREBASE_CREDENTIALS_FILE or not config.FIREBASE_PROJECT_ID:
        return None
    from firebase_admin import firestore  # type: ignore

    return FirebaseAdminFirestoreClient(firestore.client())


def create_app(config: Config | None = None) -> Flask:
    cfg = config or Config()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=cfg.SECRET_KEY,
        DATABASE_PATH=cfg.DATABASE_PATH,
        DEBOUNCE_SECONDS=cfg.DEBOUNCE_SECONDS,
        CLASSIFICATIONS=CLASSIFICATIONS,
        FIREBASE_VERIFIER=_build_firebase_verifier(cfg),
        FIRESTORE_CLIENT=_build_firestore_client(cfg),
    )

    if cfg.USE_MOCK_HARDWARE:
        app.fingerprint_sensor = MockFingerprintSensor()
        app.feedback_controller = MockFeedbackController()
    else:
        app.fingerprint_sensor = AS608SerialFingerprintSensor(AS608Config(cfg.AS608_PORT, cfg.AS608_BAUDRATE))
        app.feedback_controller = RaspberryPiFeedbackController(
            GPIOConfig(cfg.GREEN_LED_PIN, cfg.RED_LED_PIN, cfg.BUZZER_PIN)
        )

    init_db(cfg.DATABASE_PATH)

    @app.before_request
    def _db_connect() -> None:
        g.db = connect_db(app.config["DATABASE_PATH"])

    @app.teardown_request
    def _db_close(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.route("/")
    def root():
        if session.get("admin_id"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET"])
    def login():
        return render_template("login.html")

    @app.route("/auth/token", methods=["POST"])
    def auth_token():
        id_token = request.form.get("id_token", "").strip()
        if not id_token:
            flash("Firebase ID token is required.", "error")
            return redirect(url_for("login"))

        try:
            token_data = verify_admin_token(id_token)
        except AuthError as exc:
            flash(str(exc), "error")
            return redirect(url_for("login"))
        except Exception:
            flash("Failed to verify Firebase token.", "error")
            return redirect(url_for("login"))

        admin_id = token_data.get("uid") or str(uuid.uuid4())
        username = token_data.get("email") or token_data.get("name") or admin_id
        with g.db:
            g.db.execute(
                """
                INSERT INTO ADMINISTRATOR (AdminID, Username, Status)
                VALUES (?, ?, 'active')
                ON CONFLICT(AdminID) DO UPDATE SET Username = excluded.Username
                """,
                (admin_id, username),
            )

        session["admin_id"] = admin_id
        session["admin_username"] = username
        return redirect(url_for("dashboard"))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @admin_required
    def dashboard():
        member_count = g.db.execute('SELECT COUNT(*) AS c FROM "USER"').fetchone()["c"]
        attendance_count = g.db.execute("SELECT COUNT(*) AS c FROM ATTENDANCE_LOG").fetchone()["c"]
        open_sessions = g.db.execute(
            "SELECT COUNT(*) AS c FROM ATTENDANCE_LOG WHERE TimeOut IS NULL"
        ).fetchone()["c"]
        unsynced = g.db.execute(
            "SELECT COUNT(*) AS c FROM ATTENDANCE_LOG WHERE SyncStatus != 'synced'"
        ).fetchone()["c"]

        return render_template(
            "dashboard.html",
            member_count=member_count,
            attendance_count=attendance_count,
            open_sessions=open_sessions,
            unsynced=unsynced,
        )

    @app.route("/members")
    @admin_required
    def members():
        q = request.args.get("q", "").strip()
        classification = request.args.get("classification", "").strip()

        query = 'SELECT * FROM "USER" WHERE 1=1'
        params: list[str] = []
        if q:
            query += " AND Name LIKE ?"
            params.append(f"%{q}%")
        if classification in CLASSIFICATIONS:
            query += " AND Classification = ?"
            params.append(classification)
        query += " ORDER BY Name"

        rows = g.db.execute(query, params).fetchall()
        return render_template(
            "members.html",
            members=rows,
            classifications=CLASSIFICATIONS,
            selected_classification=classification,
            q=q,
        )

    def _validate_member_form(form) -> tuple[str, int, str, str] | None:
        name = form.get("name", "").strip()
        fingerprint_raw = form.get("fingerprint_id", "").strip()
        classification = form.get("classification", "").strip()
        status = form.get("status", "active").strip()

        if not name or not fingerprint_raw or classification not in CLASSIFICATIONS or status not in USER_STATUSES:
            return None

        try:
            fingerprint_id = int(fingerprint_raw)
        except ValueError:
            return None

        return name, fingerprint_id, classification, status

    @app.route("/members/new", methods=["GET", "POST"])
    @admin_required
    def new_member():
        if request.method == "POST":
            validated = _validate_member_form(request.form)
            if not validated:
                flash("Invalid member input.", "error")
                return redirect(url_for("new_member"))

            name, fingerprint_id, classification, status = validated
            user_id = str(uuid.uuid4())
            try:
                with g.db:
                    g.db.execute(
                        """
                        INSERT INTO "USER"
                        (UserID, AdminID, Name, FingerprintID, Classification, Status, EnrollmentStatus)
                        VALUES (?, ?, ?, ?, ?, ?, 'pending')
                        """,
                        (user_id, session["admin_id"], name, fingerprint_id, classification, status),
                    )
                flash("Member created.", "success")
            except sqlite3.IntegrityError:
                flash("Fingerprint ID already assigned.", "error")
            return redirect(url_for("members"))

        return render_template("member_form.html", member=None, classifications=CLASSIFICATIONS)

    @app.route("/members/<user_id>/edit", methods=["GET", "POST"])
    @admin_required
    def edit_member(user_id: str):
        member = g.db.execute('SELECT * FROM "USER" WHERE UserID = ?', (user_id,)).fetchone()
        if member is None:
            flash("Member not found.", "error")
            return redirect(url_for("members"))

        if request.method == "POST":
            validated = _validate_member_form(request.form)
            if not validated:
                flash("Invalid member input.", "error")
                return redirect(url_for("edit_member", user_id=user_id))

            name, fingerprint_id, classification, status = validated
            enrollment_status = request.form.get("enrollment_status", "pending")
            if enrollment_status not in ("pending", "enrolled"):
                enrollment_status = "pending"
            try:
                with g.db:
                    g.db.execute(
                        """
                        UPDATE "USER"
                        SET Name=?, FingerprintID=?, Classification=?, Status=?, EnrollmentStatus=?
                        WHERE UserID=?
                        """,
                        (name, fingerprint_id, classification, status, enrollment_status, user_id),
                    )
                flash("Member updated.", "success")
            except sqlite3.IntegrityError:
                flash("Fingerprint ID already assigned.", "error")
            return redirect(url_for("members"))

        return render_template("member_form.html", member=member, classifications=CLASSIFICATIONS)

    @app.route("/members/<user_id>/enroll", methods=["POST"])
    @admin_required
    def enroll_member(user_id: str):
        member = g.db.execute('SELECT * FROM "USER" WHERE UserID = ?', (user_id,)).fetchone()
        if member is None:
            flash("Member not found.", "error")
            return redirect(url_for("members"))

        try:
            ok = app.fingerprint_sensor.enroll(int(member["FingerprintID"]))
        except Exception:
            LOGGER.exception("Fingerprint enrollment failed")
            ok = False

        with g.db:
            g.db.execute(
                'UPDATE "USER" SET EnrollmentStatus=? WHERE UserID=?',
                ("enrolled" if ok else "pending", user_id),
            )

        flash("Fingerprint enrolled." if ok else "Fingerprint enrollment failed.", "success" if ok else "error")
        return redirect(url_for("members"))

    @app.route("/attendance")
    @admin_required
    def attendance():
        member = request.args.get("member", "").strip()
        classification = request.args.get("classification", "").strip()
        date_value = request.args.get("date", "").strip()

        query = (
            """
            SELECT a.LogID, u.Name, u.Classification, a.Date, a.TimeIn, a.TimeOut, a.Duration, a.SyncStatus
            FROM ATTENDANCE_LOG a
            JOIN "USER" u ON u.UserID = a.UserID
            WHERE 1=1
            """
        )
        params: list[str] = []

        if member:
            query += " AND u.Name LIKE ?"
            params.append(f"%{member}%")
        if classification in CLASSIFICATIONS:
            query += " AND u.Classification = ?"
            params.append(classification)
        if date_value:
            query += " AND a.Date = ?"
            params.append(date_value)

        query += " ORDER BY a.Date DESC, a.TimeIn DESC"

        rows = g.db.execute(query, params).fetchall()
        return render_template(
            "attendance.html",
            records=rows,
            classifications=CLASSIFICATIONS,
            filters={"member": member, "classification": classification, "date": date_value},
        )

    @app.route("/sync", methods=["POST"])
    @admin_required
    def sync():
        firestore_client = app.config.get("FIRESTORE_CLIENT")
        try:
            summary = FirestoreSyncService(g.db, firestore_client).sync()
            flash(
                f"Synced members={summary.members_synced}, attendance={summary.attendance_synced}, failures={summary.failures}",
                "success",
            )
        except FirebaseConfigError as exc:
            flash(str(exc), "error")
        except Exception:
            LOGGER.exception("Sync failed")
            flash("Sync failed. Pending local records are preserved.", "error")
        return redirect(url_for("attendance"))

    @app.route("/kiosk")
    def kiosk_page():
        return render_template("kiosk.html")

    @app.route("/kiosk/scan", methods=["POST"])
    def kiosk_scan():
        sensor = app.fingerprint_sensor
        feedback = app.feedback_controller

        try:
            fingerprint_id = sensor.identify()
        except Exception:
            LOGGER.exception("Fingerprint scan failed")
            feedback.failure()
            return jsonify({"ok": False, "message": "Sensor unavailable."}), 503

        if fingerprint_id is None:
            feedback.failure()
            return jsonify({"ok": False, "message": "Fingerprint not recognized."}), 404

        user = g.db.execute(
            'SELECT UserID, Name, Classification, Status FROM "USER" WHERE FingerprintID = ? AND Status = "active"',
            (fingerprint_id,),
        ).fetchone()

        if user is None:
            feedback.failure()
            return jsonify({"ok": False, "message": "Fingerprint not linked to an active member."}), 404

        try:
            result = record_scan(g.db, user["UserID"], app.config["DEBOUNCE_SECONDS"])
        except Exception:
            LOGGER.exception("Attendance transaction failed")
            feedback.failure()
            return jsonify({"ok": False, "message": "Failed to save attendance."}), 500

        if result.duplicate:
            feedback.failure()
            return jsonify(
                {
                    "ok": False,
                    "message": "Repeated scan ignored. Please wait before scanning again.",
                    "member": {"name": user["Name"], "classification": user["Classification"]},
                }
            ), 409

        feedback.success()
        action_label = "Time In" if result.action == "time_in" else "Time Out"
        return jsonify(
            {
                "ok": True,
                "action": action_label,
                "member": {"name": user["Name"], "classification": user["Classification"]},
            }
        )

    return app
