"""Small OSRS vision and zone debugging panel."""

from __future__ import annotations

import tkinter
from pathlib import Path

import customtkinter

from vision import VisionDebugTools
from view.fonts.fonts import body_med_font, small_font


class VisionDebugView(customtkinter.CTkToplevel):
    PROFILE_PATH = Path(__file__).resolve().parents[2] / "hsv_profiles.json"

    def __init__(self, parent, runtime):
        super().__init__(parent)
        self.runtime = runtime
        self.tools = VisionDebugTools(runtime, self.PROFILE_PATH)
        self.title("OSRS Vision Debug")
        self.geometry("480x520")
        self.resizable(False, False)
        self.zone_var = tkinter.StringVar(value="game_view")
        self.status_var = tkinter.StringVar(value="Ready")
        self._build()

    def _build(self):
        frame = customtkinter.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=15, pady=15)
        customtkinter.CTkLabel(frame, text="Vision and zone debugging", font=body_med_font()).pack(pady=(5, 12))
        customtkinter.CTkLabel(frame, text="Zone", font=small_font()).pack(anchor="w")
        customtkinter.CTkOptionMenu(
            frame,
            variable=self.zone_var,
            values=["client", "game_view", "inventory", "minimap", "chat", "mouseover"],
        ).pack(fill="x", pady=(0, 8))

        self.fields = {}
        for label, key, default in (
            ("Profile name", "name", "debug"),
            ("HSV lower (H,S,V)", "lower", "0,0,0"),
            ("HSV upper (H,S,V)", "upper", "179,255,255"),
            ("Minimum area", "min_area", "1"),
        ):
            customtkinter.CTkLabel(frame, text=label, font=small_font()).pack(anchor="w")
            entry = customtkinter.CTkEntry(frame, font=small_font())
            entry.insert(0, default)
            entry.pack(fill="x", pady=(0, 6))
            self.fields[key] = entry

        buttons = customtkinter.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", pady=6)
        customtkinter.CTkButton(buttons, text="Detect HSV", command=self.detect).pack(side="left", expand=True, padx=2)
        customtkinter.CTkButton(buttons, text="Save Profile", command=self.save_profile).pack(side="left", expand=True, padx=2)
        customtkinter.CTkButton(buttons, text="Zone Info", command=self.zone_info).pack(side="left", expand=True, padx=2)

        exclusion = customtkinter.CTkFrame(frame, fg_color="transparent")
        exclusion.pack(fill="x", pady=6)
        self.exclusion_fields = []
        for label in ("Left", "Top", "Width", "Height"):
            customtkinter.CTkLabel(exclusion, text=label, font=small_font()).pack(side="left", padx=2)
            entry = customtkinter.CTkEntry(exclusion, width=55, font=small_font())
            entry.insert(0, "0")
            entry.pack(side="left", padx=2)
            self.exclusion_fields.append(entry)
        customtkinter.CTkButton(frame, text="Add Exclusion", command=self.add_exclusion).pack(fill="x", pady=2)
        customtkinter.CTkButton(frame, text="Clear Exclusions", command=self.clear_exclusions).pack(fill="x", pady=2)
        customtkinter.CTkLabel(frame, textvariable=self.status_var, wraplength=430, font=small_font()).pack(pady=12)

    def _profile(self):
        return self.tools.profile(
            self.fields["name"].get(),
            self.fields["lower"].get(),
            self.fields["upper"].get(),
            self.fields["min_area"].get(),
        )

    def detect(self):
        try:
            profile = self._profile()
            results = self.tools.detect(self.zone_var.get(), profile)
            self.status_var.set(f"{len(results)} region(s) detected in {self.zone_var.get()}: {[result.bounds for result in results[:5]]}")
        except (ValueError, KeyError, RuntimeError) as error:
            self.status_var.set(f"Detection error: {error}")

    def save_profile(self):
        try:
            profile = self._profile()
            self.tools.save_profile(profile)
            self.status_var.set(f"Saved profile '{profile.name}' to {self.PROFILE_PATH.name}.")
        except (ValueError, OSError) as error:
            self.status_var.set(f"Profile error: {error}")

    def zone_info(self):
        try:
            info = self.tools.zone_info(self.zone_var.get())
            self.status_var.set(f"{info['name']}: {info['bounds']} | exclusions: {info['exclusion_count']}")
        except (AttributeError, RuntimeError) as error:
            self.status_var.set(f"Zone error: {error}")

    def add_exclusion(self):
        try:
            values = [int(entry.get()) for entry in self.exclusion_fields]
            self.tools.add_exclusion(self.zone_var.get(), *values)
            self.zone_info()
        except (ValueError, AttributeError, RuntimeError) as error:
            self.status_var.set(f"Exclusion error: {error}")

    def clear_exclusions(self):
        try:
            self.tools.clear_exclusions(self.zone_var.get())
            self.zone_info()
        except (AttributeError, RuntimeError) as error:
            self.status_var.set(f"Exclusion error: {error}")
