from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-change-me")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/logbook.db")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "0") == "1"

    FIREBASE_CREDENTIALS_FILE: str | None = os.getenv("FIREBASE_CREDENTIALS_FILE")
    FIREBASE_PROJECT_ID: str | None = os.getenv("FIREBASE_PROJECT_ID")

    DEBOUNCE_SECONDS: int = int(os.getenv("DEBOUNCE_SECONDS", "8"))

    USE_MOCK_HARDWARE: bool = os.getenv("USE_MOCK_HARDWARE", "1") == "1"
    AS608_PORT: str = os.getenv("AS608_PORT", "COM3")
    AS608_BAUDRATE: int = int(os.getenv("AS608_BAUDRATE", "57600"))

    GREEN_LED_PIN: int = int(os.getenv("GREEN_LED_PIN", "17"))
    RED_LED_PIN: int = int(os.getenv("RED_LED_PIN", "27"))
    BUZZER_PIN: int = int(os.getenv("BUZZER_PIN", "22"))
