"""Typed, JSON-backed configuration for runtime services."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from utilities.windmouse import WindMouseSettings
from actions.verification import RetryPolicy
from runtime.navigation import NavigationPolicy
from runtime.session import BreakPolicy, SessionBudget


@dataclass(frozen=True)
class InputSettings:
    cadence_hz: float = 60.0

    def __post_init__(self):
        if (isinstance(self.cadence_hz, bool) or not isinstance(self.cadence_hz, (int, float))
                or not math.isfinite(self.cadence_hz) or self.cadence_hz <= 0):
            raise ValueError("cadence_hz must be a positive finite number")


@dataclass(frozen=True)
class VerificationSettings:
    max_attempts: int = 1
    retry_delay_seconds: float = 0.0

    def __post_init__(self):
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise ValueError("max_attempts must be an integer")
        if (isinstance(self.retry_delay_seconds, bool) or not isinstance(self.retry_delay_seconds, (int, float))
                or not math.isfinite(self.retry_delay_seconds)):
            raise ValueError("retry_delay_seconds must be a finite number")
        RetryPolicy(self.max_attempts, self.retry_delay_seconds)

    def as_policy(self) -> RetryPolicy:
        return RetryPolicy(self.max_attempts, self.retry_delay_seconds)


@dataclass(frozen=True)
class SessionSettings:
    enabled: bool = False
    budget: SessionBudget = field(default_factory=SessionBudget)
    break_policy: BreakPolicy | None = None


@dataclass
class RuntimeConfig:
    process_id: int | None = None
    dll_path: str | None = None
    windmouse: WindMouseSettings = field(default_factory=WindMouseSettings)
    input: InputSettings = field(default_factory=InputSettings)
    verification: VerificationSettings = field(default_factory=VerificationSettings)
    navigation: NavigationPolicy = field(default_factory=NavigationPolicy)
    session: SessionSettings = field(default_factory=SessionSettings)
    telemetry_enabled: bool = False
    telemetry_capacity: int = 512

    def __post_init__(self) -> None:
        if self.process_id is not None and (isinstance(self.process_id, bool) or not isinstance(self.process_id, int)
                                            or self.process_id < 1):
            raise ValueError("process_id must be a positive integer")
        if (isinstance(self.telemetry_capacity, bool) or not isinstance(self.telemetry_capacity, int)
                or self.telemetry_capacity < 1):
            raise ValueError("telemetry_capacity must be a positive integer")
        if not isinstance(self.telemetry_enabled, bool):
            raise ValueError("telemetry_enabled must be a boolean")

    def save(self, path: str | Path) -> None:
        payload = asdict(self)
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "RuntimeConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        windmouse = WindMouseSettings(**payload.pop("windmouse", {}))
        input_settings = InputSettings(**payload.pop("input", {}))
        verification = VerificationSettings(**payload.pop("verification", {}))
        navigation = NavigationPolicy(**payload.pop("navigation", {}))
        session_payload = payload.pop("session", {})
        budget = SessionBudget(**session_payload.pop("budget", {}))
        break_payload = session_payload.pop("break_policy", None)
        break_policy = BreakPolicy(**break_payload) if break_payload else None
        session = SessionSettings(budget=budget, break_policy=break_policy, **session_payload)
        return cls(windmouse=windmouse, input=input_settings, verification=verification,
                   navigation=navigation, session=session, **payload)
