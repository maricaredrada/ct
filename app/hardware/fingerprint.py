from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

LOGGER = logging.getLogger(__name__)

try:
    import serial  # type: ignore
except Exception:  # pragma: no cover - allows windows tests without pyserial runtime
    serial = None


class FingerprintError(RuntimeError):
    pass


class FingerprintSensor:
    def enroll(self, fingerprint_id: int) -> bool:
        raise NotImplementedError

    def identify(self) -> Optional[int]:
        raise NotImplementedError


@dataclass
class AS608Config:
    port: str
    baudrate: int = 57600
    timeout: float = 1.0


class AS608SerialFingerprintSensor(FingerprintSensor):
    """
    Minimal UART implementation for AS608-compatible modules.

    Expected wiring/protocol:
    - UART TTL serial
    - 57600 baud (default)
    - Packets starting with 0xEF01 header and command payloads.

    This implementation provides a defensive baseline and should be validated on actual hardware.
    """

    def __init__(self, config: AS608Config):
        if serial is None:
            raise FingerprintError("PySerial is not available")
        self.config = config

    def _open(self):
        try:
            return serial.Serial(self.config.port, self.config.baudrate, timeout=self.config.timeout)
        except Exception as exc:
            raise FingerprintError(f"AS608 not reachable on {self.config.port}") from exc

    def enroll(self, fingerprint_id: int) -> bool:
        # Placeholder command envelope for hardware workflow demonstration.
        # Actual enrollment steps depend on capture twice -> model -> store.
        if fingerprint_id < 0:
            raise FingerprintError("Invalid fingerprint_id")
        with self._open() as ser:
            ser.write(f"ENROLL:{fingerprint_id}\n".encode("ascii"))
            response = ser.readline().decode("ascii", errors="ignore").strip()
            return response == "OK"

    def identify(self) -> Optional[int]:
        with self._open() as ser:
            ser.write(b"IDENTIFY\n")
            response = ser.readline().decode("ascii", errors="ignore").strip()
            if not response:
                return None
            if response.startswith("ID:"):
                try:
                    return int(response.split(":", 1)[1])
                except ValueError:
                    LOGGER.warning("Malformed AS608 response: %s", response)
                    return None
            return None


class MockFingerprintSensor(FingerprintSensor):
    def __init__(self) -> None:
        self._enrolled: set[int] = set()
        self._next_identify: Optional[int] = None

    def set_next_identify(self, fingerprint_id: Optional[int]) -> None:
        self._next_identify = fingerprint_id

    def enroll(self, fingerprint_id: int) -> bool:
        self._enrolled.add(fingerprint_id)
        return True

    def identify(self) -> Optional[int]:
        result = self._next_identify
        self._next_identify = None
        if result in self._enrolled:
            return result
        return None
