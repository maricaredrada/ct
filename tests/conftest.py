from __future__ import annotations

import uuid

import pytest

from app import create_app
from app.config import Config
from app.db import connect_db


@pytest.fixture
def test_config(tmp_path):
    return Config(
        SECRET_KEY="test",
        DATABASE_PATH=str(tmp_path / "test.db"),
        DEBUG=True,
        FIREBASE_CREDENTIALS_FILE=None,
        FIREBASE_PROJECT_ID=None,
        DEBOUNCE_SECONDS=30,
        USE_MOCK_HARDWARE=True,
        AS608_PORT="COM1",
        AS608_BAUDRATE=57600,
        GREEN_LED_PIN=17,
        RED_LED_PIN=27,
        BUZZER_PIN=22,
    )


@pytest.fixture
def app(test_config):
    app = create_app(test_config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def db_conn(app):
    conn = connect_db(app.config["DATABASE_PATH"])
    admin_id = str(uuid.uuid4())
    with conn:
        conn.execute(
            "INSERT INTO ADMINISTRATOR (AdminID, Username, Status) VALUES (?, ?, 'active')",
            (admin_id, "admin@example.com"),
        )
    yield conn, admin_id
    conn.close()
