from __future__ import annotations

from dataclasses import dataclass

try:
    from gpiozero import Buzzer, LED  # type: ignore
except Exception:  # pragma: no cover - allows non-Pi environments
    LED = None
    Buzzer = None


class FeedbackController:
    def success(self) -> None:
        raise NotImplementedError

    def failure(self) -> None:
        raise NotImplementedError


@dataclass
class GPIOConfig:
    green_pin: int
    red_pin: int
    buzzer_pin: int


class RaspberryPiFeedbackController(FeedbackController):
    def __init__(self, config: GPIOConfig):
        if LED is None or Buzzer is None:
            raise RuntimeError("gpiozero is not available")
        self.green = LED(config.green_pin)
        self.red = LED(config.red_pin)
        self.buzzer = Buzzer(config.buzzer_pin)

    def _beep(self, repeat: int) -> None:
        for _ in range(repeat):
            self.buzzer.on()
            self.buzzer.off()

    def success(self) -> None:
        self.green.on()
        self.red.off()
        self._beep(1)
        self.green.off()

    def failure(self) -> None:
        self.red.on()
        self.green.off()
        self._beep(2)
        self.red.off()


class MockFeedbackController(FeedbackController):
    def __init__(self) -> None:
        self.events: list[str] = []

    def success(self) -> None:
        self.events.append("success")

    def failure(self) -> None:
        self.events.append("failure")
