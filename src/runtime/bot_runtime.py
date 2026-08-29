"""Minimal runtime that coordinates client, input, actions, and vision services."""

from __future__ import annotations

from actions import GameActions
from client import RuneLiteClient
from utilities.input import InputProvider, InputProviderError
from utilities.mouse import Mouse
from vision import VisionService


class BotRuntime:
    def __init__(self, window, mouse: Mouse) -> None:
        self.client = RuneLiteClient(window)
        self.mouse = mouse
        self.input_provider: InputProvider | None = None
        self.actions = GameActions(mouse)
        self.vision = VisionService(self.client.zones)

    def set_input_provider(self, provider: InputProvider) -> None:
        self.input_provider = provider
        self.actions.input_provider = provider

    def start(self) -> None:
        if self.input_provider is None:
            raise InputProviderError("RemoteInput is not configured for this bot. Direct desktop input is disabled.")
        origin = self.client.initialize()
        self.input_provider.connect()
        self.mouse.set_input_provider(self.input_provider, origin)

    def stop(self) -> None:
        if self.input_provider is not None:
            self.input_provider.disconnect()
