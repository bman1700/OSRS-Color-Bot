"""Minimal runtime that coordinates client, input, actions, and vision services."""

from __future__ import annotations

from actions import GameActions
from client import RuneLiteClient
from utilities.input import InputProvider, InputProviderError, RemoteInputProvider
from utilities.mouse import Mouse
from vision import VisionService
from runtime.config import RuntimeConfig
from runtime.sensors import SensorService
from runtime.events import RuntimeEventBus
from pathlib import Path


class BotRuntime:
    def __init__(self, window, mouse: Mouse) -> None:
        self.client = RuneLiteClient(window)
        self.mouse = mouse
        self.input_provider: InputProvider | None = None
        self.actions = GameActions(mouse)
        self.vision = VisionService(self.client.zones)
        self.sensors = SensorService()
        self.events = RuntimeEventBus()

    def emit(self, name: str, payload=None) -> None:
        self.events.emit(name, payload)

    def attach_sensor_source(self, source) -> None:
        self.sensors.attach_source(source)

    def snapshot(self):
        return self.sensors.snapshot()

    def save_config(self, path: str | Path | None = None) -> None:
        provider = self.input_provider
        config_path = Path(path or Path(__file__).resolve().parents[2] / "runtime_config.json")
        RuntimeConfig(
            process_id=getattr(provider, "process_id", None),
            dll_path=str(getattr(provider, "dll_path", "")) if provider is not None else None,
            windmouse=self.mouse.windmouse_settings,
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
        health_check = getattr(self.input_provider, "health_check", None)
        if health_check is not None and not health_check():
            self.input_provider.disconnect()
            raise InputProviderError("RemoteInput connected but failed its health check")
        self.emit("input_health", True)

    def stop(self) -> None:
        if self.input_provider is not None:
            self.input_provider.disconnect()
        self.emit("runtime_stopped")
