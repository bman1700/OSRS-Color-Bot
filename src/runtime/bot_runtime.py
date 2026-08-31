"""Minimal runtime that coordinates client, input, actions, and vision services."""

from __future__ import annotations

from actions import GameActions
from client import RuneLiteClient
from utilities.input import InputProvider, InputProviderError, RemoteInputProvider
from utilities.mouse import Mouse
from utilities.red_click import RedClickVerifier
from vision import VisionService
from runtime.config import InputSettings, RuntimeConfig, SessionSettings, VerificationSettings
from runtime.sensors import SensorService
from runtime.events import RuntimeEventBus
from runtime.session import BreakPolicy, SessionBudget, SessionPlanner
from runtime.telemetry import TelemetryRecorder
from runtime.locations import BankLocation, BankLocationRegistry
from runtime.navigation import (MinimapNavigator, NavigationPolicy, NullPathProvider,
                                PathProvider, SensorCompass, SnapshotTilePosition,
                                WindowMinimapProjector, Tile)
from pathlib import Path


class BotRuntime:
    def __init__(self, window, mouse: Mouse, *, telemetry: TelemetryRecorder | None = None) -> None:
        self.client = RuneLiteClient(window)
        self.mouse = mouse
        self.mouse.set_layout_refresh(self._refresh_layout_for_input)
        self.input_provider: InputProvider | None = None
        self.actions = GameActions(mouse)
        self.vision = VisionService(self.client.zones)
        self.sensors = SensorService()
        self.events = RuntimeEventBus()
        # Disabled by default; scripts must explicitly query/use this planner.
        self.session_planner = SessionPlanner(events=self.events)
        # Disabled by default: diagnostics never create files or network traffic.
        self.telemetry = telemetry or TelemetryRecorder()
        self.navigation_policy = RuntimeConfig().navigation
        self.verification_policy = RuntimeConfig().verification.as_policy()
        self.navigator: MinimapNavigator | None = None
        self.path_provider: PathProvider = NullPathProvider()
        self.bank_locations = BankLocationRegistry.from_builtin()

    def _refresh_layout_for_input(self, point: tuple[int, int]) -> tuple[int, int] | None:
        """Refresh tab geometry when input is aimed at a tab band.

        RuneLite's right sidebar can open or close independently of the game
        process. Only tab-band input triggers the refresh so normal gameplay
        movement does not pay the screenshot/template-detection cost.
        """
        tabs = getattr(self.client.window, "cp_tabs", ())
        if not tabs:
            return None
        x, y = point
        for tab_index, tab in enumerate(tabs):
            if tab.left - 18 <= x <= tab.left + tab.width + 18 and tab.top - 18 <= y <= tab.top + tab.height + 18:
                try:
                    self.client.window.initialize()
                    print("Runtime refreshed RuneLite layout before tab input.", flush=True)
                    refreshed_tabs = getattr(self.client.window, "cp_tabs", ())
                    if tab_index < len(refreshed_tabs):
                        return refreshed_tabs[tab_index].get_center()
                except Exception as error:
                    print(f"Runtime could not refresh RuneLite layout before tab input: {error}", flush=True)
                return None
        return None

    def get_bank_location(self, name: str) -> BankLocation:
        """Return a named shared bank destination for a script."""
        return self.bank_locations.get(name)

    def save_bank_locations(self, path: str | Path | None = None) -> None:
        """Persist the shared bank registry without changing runtime config."""
        location_path = Path(path or Path(__file__).resolve().parents[2] / "bank_locations.json")
        self.bank_locations.save(location_path)

    def emit(self, name: str, payload=None) -> None:
        self.events.emit(name, payload)

    def configure_session(
        self, budget: SessionBudget | None = None, break_policy: BreakPolicy | None = None
    ) -> SessionPlanner:
        """Configure the opt-in planner without changing current script flow."""
        self.session_planner = SessionPlanner(budget, break_policy, events=self.events)
        return self.session_planner

    def enable_telemetry(self, *, capacity: int | None = None) -> TelemetryRecorder:
        """Enable bounded in-memory diagnostics for the current runtime."""
        if capacity is not None and capacity != self.telemetry.capacity:
            self.telemetry = TelemetryRecorder(capacity=capacity, enabled=True)
        else:
            self.telemetry.set_enabled(True)
        return self.telemetry

    def record_telemetry(self, kind: str, *, action: str | None = None, data=None):
        """Record a diagnostic fact and notify observers when telemetry is enabled."""
        record = self.telemetry.record(kind, action=action, data=data)
        if record is not None:
            self.emit("telemetry", record)
        return record

    def record_action_intent(self, action: str, *, target=None, metadata=None):
        data = dict(metadata or {})
        if target is not None:
            data["target"] = target
        return self.record_telemetry("action_intent", action=action, data=data)

    def record_detection(self, name: str, confidence: float | None, *, metadata=None):
        data = dict(metadata or {})
        data.update(name=name, confidence=confidence)
        return self.record_telemetry("detection", data=data)

    def record_wait(self, predicate: str, elapsed_seconds: float, outcome: str, *, metadata=None):
        data = dict(metadata or {})
        data.update(predicate=predicate, elapsed_seconds=elapsed_seconds, outcome=outcome)
        return self.record_telemetry("wait", data=data)

    def record_verification(self, action: str, *, succeeded: bool, attempts: int, reason: str, metadata=None):
        data = dict(metadata or {})
        data.update(succeeded=succeeded, attempts=attempts, reason=reason)
        return self.record_telemetry("verification", action=action, data=data)

    def record_recovery(self, action: str, reason: str, *, metadata=None):
        data = dict(metadata or {})
        data["reason"] = reason
        return self.record_telemetry("recovery", action=action, data=data)

    def attach_sensor_source(self, source) -> None:
        self.sensors.attach_source(source)

    def configure_navigation(
        self,
        path_provider: PathProvider | None = None,
        *,
        position=None,
        pixels_per_tile: float = 4.0,
        policy: NavigationPolicy | None = None,
    ) -> MinimapNavigator:
        """Create the shared navigator with an injectable route provider.

        This remains usable without DAX or any other external service: callers
        may inject a local provider, while the default provider safely returns
        ``NO_PATH``.  Position defaults to the optional status source.
        """
        self.path_provider = path_provider or NullPathProvider()
        position = position or (SnapshotTilePosition(self.snapshot) if self.sensors.source else (lambda: None))
        compass = SensorCompass(self.snapshot if self.sensors.source else None)
        projector = WindowMinimapProjector(self.client.window, compass, pixels_per_tile)

        def click(point: tuple[int, int]) -> None:
            self.mouse.move_to(point)
            self.mouse.click()

        self.navigator = MinimapNavigator(position, self.path_provider, projector, click,
                                          policy=policy or self.navigation_policy)
        return self.navigator

    def walk_to(self, destination: Tile):
        """Walk using the configured navigator; unconfigured navigation fails closed."""
        navigator = self.navigator or self.configure_navigation()
        return navigator.walk_to(destination)

    def snapshot(self):
        return self.sensors.snapshot()

    def temporal_sensors(self, *, stale_after: float | None = None):
        """Expose temporal sensor predicates to scripts."""
        from runtime.temporal import TemporalSensors
        return TemporalSensors(self.snapshot, stale_after=stale_after)

    def save_config(self, path: str | Path | None = None) -> None:
        provider = self.input_provider
        config_path = Path(path or Path(__file__).resolve().parents[2] / "runtime_config.json")
        RuntimeConfig(
            process_id=getattr(provider, "process_id", None),
            dll_path=str(getattr(provider, "dll_path", "")) if provider is not None else None,
            windmouse=self.mouse.windmouse_settings,
            input=InputSettings(cadence_hz=self.mouse.input_executor.cadence_hz),
            verification=VerificationSettings(
                max_attempts=self.verification_policy.max_attempts,
                retry_delay_seconds=self.verification_policy.retry_delay_seconds,
            ),
            navigation=self.navigation_policy,
            session=SessionSettings(
                enabled=self.session_planner.break_policy is not None or self.session_planner.budget.max_session_seconds is not None,
                budget=self.session_planner.budget,
                break_policy=self.session_planner.break_policy,
            ),
            telemetry_enabled=self.telemetry.enabled,
            telemetry_capacity=self.telemetry.capacity,
        ).save(config_path)
        self.emit("config_saved", str(config_path))

    def load_config(self, path: str | Path | None = None) -> RuntimeConfig | None:
        config_path = Path(path or Path(__file__).resolve().parents[2] / "runtime_config.json")
        if not config_path.is_file():
            return None
        try:
            config = RuntimeConfig.load(config_path)
            self.apply_config(config)
            self.emit("config_loaded", str(config_path))
            return config
        except (OSError, ValueError, TypeError):
            self.emit("config_error", f"Unable to load runtime configuration: {config_path}")
            return None

    def apply_config(self, config: RuntimeConfig) -> None:
        """Apply persisted movement settings before a bot starts."""
        self.mouse.set_windmouse_settings(config.windmouse)
        self.mouse.set_input_cadence(config.input.cadence_hz)
        self.verification_policy = config.verification.as_policy()
        self.navigation_policy = config.navigation
        if config.session.enabled:
            self.configure_session(config.session.budget, config.session.break_policy)
        else:
            self.session_planner = SessionPlanner(events=self.events)
        if config.telemetry_capacity != self.telemetry.capacity:
            self.telemetry = TelemetryRecorder(capacity=config.telemetry_capacity, enabled=config.telemetry_enabled)
        else:
            self.telemetry.set_enabled(config.telemetry_enabled)
        if config.process_id is not None:
            self.set_input_provider(RemoteInputProvider(process_id=config.process_id, dll_path=config.dll_path))
        self.emit("config_applied", config)

    def set_input_provider(self, provider: InputProvider) -> None:
        self.input_provider = provider
        self.actions.input_provider = provider

    def start(self) -> None:
        if self.input_provider is None:
            raise InputProviderError("RemoteInput is not configured for this bot. Direct desktop input is disabled.")
        origin = self.client.initialize()
        self.emit("client_initialized", origin)
        self.input_provider.connect()
        self.mouse.set_input_provider(self.input_provider, origin)
        window_origin = self.client.window.position()
        self.mouse.set_red_click_verifier(
            RedClickVerifier(self.client.window.rectangle().screenshot, (window_origin.x, window_origin.y))
        )
        health_check = getattr(self.input_provider, "health_check", None)
        if health_check is not None and not health_check():
            self.input_provider.disconnect()
            raise InputProviderError("RemoteInput connected but failed its health check")
        self.emit("input_health", True)

    def stop(self) -> None:
        # Cancel any in-flight or queued paced input before tearing down the
        # provider.  Otherwise the executor worker can race a disconnect and
        # deliver a native command through a stale target.
        cancel_input = getattr(self.mouse, "cancel_pending_input", None)
        if cancel_input is not None:
            cancel_input()
        if self.input_provider is not None:
            self.input_provider.disconnect()
        self.emit("runtime_stopped")
