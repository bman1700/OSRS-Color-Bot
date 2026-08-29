# ChromaScape Feature Port Plan for OS-Bot-COLOR

## Goal

Modernize this Python OSBC fork by porting the most valuable ChromaScape concepts while preserving existing scripts where practical.

The project must remain pixel/color based. Game-client input must use RemoteInput; the bot runtime must not send direct desktop mouse or keyboard input into RuneLite through PyAutoGUI, `pynput`, `PostMessage`, or similar fallbacks.

RemoteInput is a native Java-process integration, so the Python implementation will require an adapter around a compiled RemoteInput component, helper process, or native library. It is not a pure-Python replacement for PyAutoGUI.

## Implementation progress (2026-08-28)

### Completed: RemoteInput foundation and legacy action routing

- Added an `InputProvider` abstraction with `MockInputProvider` for tests and `RemoteInputProvider` for production.
- Integrated Brandon-T's 64-bit `libRemoteInput-x86_64.dll` directly through `ctypes`.
- The provider injects into the selected RuneLite Java process with `EIOS_Inject_PID`, attaches with `EIOS_RequestTarget`, and routes mouse and keyboard events through the native `EIOS_*` API.
- Confirmed a live RuneLite connection: injection, attachment, health check, and virtual pointer movement succeeded against a running Java process.
- Added a safe movement-only diagnostic script at `scripts/test_remote_input.py`.
- Added a persistent **RemoteInput PID** field to the existing UI; Play and the configured hotkey validate the PID and configure RemoteInput before bot startup.
- Converted the shared `Mouse` service to provider-only input. Existing `move_to`, `move_rel`, `click`, and `right_click` script calls now route through RemoteInput and translate existing screen coordinates to RuneLite canvas coordinates.
- Bot startup fails closed if RemoteInput is not configured or cannot attach.
- Replaced active direct PyAutoGUI mouse/keyboard calls in the production bot paths that were identified during the migration. Remaining PyAutoGUI use is limited to non-input screen/color reads and commented legacy examples.
- Added unit coverage for provider behavior and screen-to-client coordinate translation; the current suite passes (`5 passed`).

### Still pending

- Validate RemoteInput with each supported script/client combination and calibrate coordinate origin for all RuneLite layouts.
- Add explicit configuration persistence/diagnostics beyond the current UI PID field.
- Add UI persistence for WindMouse settings and migrate scripts to use it where desired.
- **Complete initial zone exclusions, containment helpers, and detector hooks;** structured detection results and richer topology management remain pending.
- Implement HSV vision, runtime restructuring, sensor state, and remaining script/UI migration phases below.

### In progress: WindMouse and topology-zone foundations

- Added a transport-independent `generate_path` WindMouse implementation with bounded settings and deterministic test support.
- Added `Mouse.move_to(..., strategy="windmouse")`; every generated point is delivered through the configured input provider.
- Added configurable movement settings through `Mouse.set_movement_strategy`, `Mouse.set_windmouse_settings`, and `Bot.configure_movement`.
- Added live `Zone` and `ZoneSet` objects at `utilities.zones`. `Window.zones` currently exposes client, game view, inventory/control panel, minimap, chat, and mouseover zones.
- Zones provide current-rectangle lookup, screenshot delegation, screen/zone-relative coordinate conversion, exclusion masking, containment checks, and caller-supplied zone-scoped detector hooks. They automatically resolve new window rectangles after client reinitialization.
- Added `HSVColorProfile`, RGB-to-HSV conversion, hue-wrap-aware masking, optional morphology cleanup, connected-component region extraction, and random region-point selection in `utilities.hsv_color`.
- Added `HSVProfileStore` JSON persistence and tests for masking, region extraction, point selection, and profile round trips.

### In progress: lightweight runtime and layer separation

- Added `runtime.BotRuntime` as the central lifecycle/service coordinator. It owns client initialization, RemoteInput connection, and exposes action and vision services.
- Added a `client.RuneLiteClient` wrapper around the existing window/zone initialization logic.
- Added `actions.GameActions` for high-level click and key actions backed by the configured input provider.
- Added `vision.VisionService` for HSV detection scoped to named zones.
- Added `domain` and `scripts` package boundaries for incremental migration; existing script files remain in place to avoid a broad rewrite.
- Existing `Bot` instances now expose `runtime` and delegate startup/shutdown to it while retaining their current API and UI integration.

## Priorities

### 1. RemoteInput backend

Create an input-provider abstraction so scripts do not depend directly on PyAutoGUI.

Planned providers:

- `RemoteInputProvider` — production game-client input path.
- `MockInputProvider` — testing provider that records actions without sending input.
- Optional desktop provider only for development tools, never as an automatic bot fallback.

The RemoteInput provider must support:

- Attaching to the RuneLite Java process.
- Mouse movement.
- Mouse button down/up and clicks.
- Keyboard key down/up.
- Connection health checks.
- Startup, shutdown, timeout, and error handling.
- Running RuneLite minimized or in the background.

The default production configuration should require RemoteInput and fail clearly if it is unavailable.

Likely locations:

- `src/utilities/input/`
- `src/utilities/mouse/`
- `src/utilities/keyboard.py`
- Native helper files under `third_party/` or a documented external dependency directory.

Before implementation, inspect the current RemoteInput source and ChromaScape integration to determine whether the bridge should use `ctypes`, IPC, a subprocess, or a Python extension.

### 2. WindMouse movement

Add WindMouse as a selectable movement strategy. The movement algorithm calculates a path; the configured input provider delivers that path to RuneLite.

The interface should support:

```python
mouse.move_to(point, strategy="windmouse", speed="medium")
```

Configurable parameters should include gravity, wind, step size, speed, endpoint variance, and timeout.

WindMouse is a movement strategy, not a guarantee against detection or account penalties.

Likely locations:

- `src/utilities/mouse/provider.py`
- `src/utilities/mouse/bezier.py`
- `src/utilities/mouse/windmouse.py`

### 3. Topology Zones

Promote meaningful client regions to first-class zone objects instead of scattering screen rectangles throughout scripts.

Initial zones:

- Game view.
- Inventory/control panel.
- Minimap.
- Chat box.
- Mouse-over text area.
- RuneLite overlay/client area.

Each zone should provide:

- A current rectangle.
- Screenshot capture.
- Zone-relative and screen-relative coordinate conversion.
- Optional exclusion/subtraction regions.
- Detection helpers scoped to that region.
- Reinitialization when the client moves or resizes.

Example:

```python
image = controller.zones.game_view.screenshot()
point = controller.vision.random_point_in_color(image, "cyan_ore")
screen_point = controller.zones.game_view.to_screen(point)
controller.mouse.move_to(screen_point)
```

Likely locations:

- `src/model/zones/`
- `src/utilities/geometry.py`
- `src/utilities/window.py`
- `src/model/runelite_bot.py`

### 4. HSV color system

Complement exact RGB matching with reusable HSV color profiles and tolerance ranges.

A color profile should contain:

- Name/identifier.
- Target HSV value.
- Lower and upper HSV bounds.
- Minimum cluster or contour size.
- Optional morphology settings.

The system should support:

- RGB-to-HSV conversion.
- Mask generation.
- Tolerance handling.
- Morphological cleanup.
- Connected-component and contour filtering.
- Random point selection within detected regions.
- Saved color profiles.
- A color-picker/debugging workflow.

Likely locations:

- `src/utilities/color.py`
- `src/model/vision/colors.py`
- `src/images/colors/` or a configurable data directory.

## Architecture modernization

### 5. Central controller/runtime layer

Separate bot execution from the UI and individual scripts.

The controller should coordinate:

- Bot lifecycle.
- RemoteInput.
- Screenshots and zones.
- Vision and OCR services.
- Configuration.
- Logging and status.
- Sensors and notifications.

Target flow:

```text
Bot script
   |
Controller
   |-- Input service
   |-- Zone service
   |-- Vision service
   |-- OCR service
   |-- Configuration service
   `-- Logging/status service
```

### 6. Separate domain, vision, actions, runtime, and client layers

Organize the framework into clearer responsibilities:

- `domain` — OSRS concepts such as inventory, NPCs, items, and player state.
- `vision` — colors, contours, image matching, OCR, and detection.
- `actions` — clicking, dragging, typing, walking, and interacting.
- `runtime` — controller, lifecycle, scheduling, and status.
- `client` — RuneLite window discovery and zone initialization.
- `scripts` — individual bot behaviors.

### 7. Structured detection results

Replace raw points, arrays, and contours with reusable result objects containing:

- Found/not-found state.
- Bounds.
- Center.
- Suggested click point.
- Confidence or match score.
- Detection source/color profile.
- Optional debug image or mask.

This gives scripts consistent handling for missing, obstructed, or ambiguous matches.

### 8. Sensor/state layer

Provide standardized observable state snapshots for scripts, including:

- Player status.
- HP, prayer, run energy, and special energy.
- Inventory occupancy.
- Nearby detected objects/NPCs.
- Active tab.
- Chat/status text.
- Combat indicators.
- Minimap information.

Scripts should consume state through this layer instead of duplicating screenshot and OCR logic.

### 9. Persistent typed configuration

Modernize the options system so settings can be validated, saved, loaded, typed, and versioned.

Configuration should eventually cover:

- RemoteInput path and process settings.
- Input backend selection.
- WindMouse parameters.
- HSV profiles.
- Zone settings.
- Script-specific options.

### 10. UI/runtime decoupling

Keep the existing CustomTkinter UI initially, but have it communicate with the runtime through controller methods and events rather than directly manipulating bot internals.

This preserves the current UI while leaving room for a future local web control panel similar to ChromaScape.

## Implementation phases

### Phase 1 — Foundations

- Define interfaces for input, movement, screenshots, zones, colors, and detection. **Input provider interface complete; other interfaces pending.**
- Preserve current behavior through compatibility adapters where safe.
- Add mockable services and geometry tests.

### Phase 2 — RemoteInput and input modernization

- Inspect and select the official RemoteInput integration mechanism. **Complete: native DLL `ctypes` integration selected.**
- Add the input-provider interface. **Complete.**
- Implement the native RemoteInput adapter. **Complete for Windows x64 DLL exports used by mouse/keyboard actions.**
- Remove direct PyAutoGUI game actions from the production path. **Complete for identified active mouse/keyboard paths; per-script validation remains.**
- Add connection diagnostics and a mock provider. **Complete: mock provider, health check, movement-only diagnostic script, and UI PID validation.**
- Verify minimized/background RuneLite operation. **Pending live validation.**

### Phase 3 — WindMouse

- Implement WindMouse independently of input transport. **Initial path generator complete.**
- Connect it to `RemoteInputProvider`. **Complete through the shared `Mouse` provider boundary.**
- Add configurable movement settings.
- **Pending UI/config persistence.**
- Keep the existing Bezier implementation only as an explicitly selected legacy strategy.
- **Superseded: desktop Bezier delivery was removed from production game actions.**

### Phase 4 — Zones and HSV vision

- Extract current `Window` rectangles into zone objects. **Initial `Window.zones` implementation complete.**
- Add coordinate transforms.
- **Complete for screen/zone-relative conversions.**
- Add exclusion/subtraction regions. **Initial masking support complete.**
- Add zone-scoped detection helpers. **Caller-supplied detector hook complete; structured results remain pending.**
- Add HSV profiles and masking. **Initial implementation complete in `utilities.hsv_color`; profile UI and broader integration remain pending.**
- Add point selection and structured detection results. **Color-region point selection complete; unified detection-result objects remain pending.**
- Add screenshot fixtures and vision tests. **Unit fixtures/tests added; real screenshot regression fixtures remain pending.**

### Phase 5 — Runtime architecture

- Introduce the controller/service structure. **Initial lightweight `BotRuntime` and service facades complete.**
- Add sensor snapshots.
- Move direct utility calls out of scripts where practical. **Initial action/vision paths are available; the woodcutter now uses them for inventory/tree interaction and tagged-tree discovery.**
- Support scaled RuneLite layouts. **Added a geometry fallback calibrated for the captured 1521x844 RuneLite layout with the sidebar enabled.**
- Decouple UI callbacks from bot implementation details. **Bot lifecycle now delegates through runtime; full event-based UI decoupling pending.**

### Phase 6 — Script and UI migration

- Migrate one example script first, preferably mining or woodcutting. **Complete: woodcutter uses `runtime.actions` for input and `runtime.vision` with a named HSV tagged-tree profile.**
- Update remaining scripts incrementally.
- Add UI controls for RemoteInput, movement strategy, HSV profiles, and zone debugging.
- Maintain compatibility helpers for older scripts during migration.

### Phase 7 — Stabilization and documentation

- Add unit tests and screenshot-based regression tests.
- Add RemoteInput setup and troubleshooting documentation.
- Add a native dependency/build guide.
- Add a new-script tutorial using the controller, zones, HSV detection, and RemoteInput APIs.
- Document the security, reliability, and account-risk limitations clearly.

## Success criteria

- No production bot action sends direct mouse or keyboard input through PyAutoGUI or equivalent desktop APIs.
- RuneLite can remain minimized while the bot operates through RemoteInput.
- Existing screenshots and vision utilities remain usable during migration.
- A migrated sample script uses controller services rather than low-level globals.
- Input, zones, colors, and detection can be tested without a live RuneLite session.
- RemoteInput failure prevents accidental fallback to direct game-client input.
