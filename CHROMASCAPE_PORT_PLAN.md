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
- Revalidated live RemoteInput against RuneLite PID 26448 at client-relative coordinates `(100,100)`, `(600,400)`, and `(1200,800)`; all connection, health, and movement checks passed.
- Added a safe movement-only diagnostic script at `scripts/test_remote_input.py`.
- Added a persistent **RemoteInput PID** field to the existing UI; Play and the configured hotkey validate the PID and configure RemoteInput before bot startup.
- Converted the shared `Mouse` service to provider-only input. Existing `move_to`, `move_rel`, `click`, and `right_click` script calls now route through RemoteInput and translate existing screen coordinates to RuneLite canvas coordinates.
- Bot startup fails closed if RemoteInput is not configured or cannot attach.
- Replaced active direct PyAutoGUI mouse/keyboard calls in the production bot paths that were identified during the migration. Remaining PyAutoGUI use is limited to non-input screen/color reads and commented legacy examples.
- Added unit coverage for provider behavior and screen-to-client coordinate translation; the current suite passes (`5 passed`).

### Completed active migration work

1. **Vision improvements**
   - Add structured OCR results. **Complete through `VisionService.find_text`.**
   - Improve object metadata and confidence scoring. **Pixel-count metadata and fill-ratio confidence are complete.**
   - Add real RuneLite screenshot regression fixtures. **Complete: `tests/fixtures/runelite_client.png` is captured and covered by a regression test.**
   - Expand zone, overlay, and scaled-layout support. **Zone reference scaling and screen-overlay exclusions are complete; live layout validation is deferred.**

2. **Sensor layer**
   - Connect `SensorService` to live StatusSocket data. **Source attachment, runtime access, and `StatusSocket.get_snapshot` are complete.**
   - Add HP, prayer points, special energy, active tab, chat, minimap, NPC, and object state. **Complete.**
   - Replace duplicated script-specific status checks. **All scripts that create a StatusSocket now attach it to the shared sensor source; common inventory/idle checks use runtime snapshots.**

3. **UI/runtime cleanup**
   - Expand runtime events to cover configuration, diagnostics, and client lifecycle. **Core status, progress, logging, clear-log, configuration, client, and input-health events are complete.**
   - Remove remaining UI assumptions about bot internals. **Controller subscriptions consume event payloads for status/progress, rather than reading bot state for runtime-originated updates.**
   - Add thread-safe UI event dispatch where needed. **Runtime events now dispatch through the UI event loop.**

4. **Configuration UI**
   - Add WindMouse parameter controls. **Basic gravity, wind, and max-step controls are complete.**
   - Add RemoteInput DLL/PID diagnostics. **PID/DLL fields and post-connect health diagnostics are complete.**
   - Connect typed JSON configuration to the UI. **UI save flow writes and controller setup loads typed `runtime_config.json`; malformed configuration is reported without crashing the UI.**
   - Movement strategy selection remains intentionally unsupported; WindMouse is mandatory.

### Deferred

- Broader live RemoteInput validation across every script. **Complete for the two remaining OSRS scripts using the non-invasive validator; the current RuneLite layout, resolution, scaling, and overlay setup remains the only supported default.**

### Completed: runtime configuration and sensors (2026-08-29)

- Added JSON-backed typed `RuntimeConfig` for RemoteInput process/DLL settings and movement/WindMouse settings.
- Added `BotRuntime.apply_config` to apply persisted movement settings and configure RemoteInput.
- Added `SensorSnapshot` and `SensorService` for normalized tick, run energy, prayer, inventory, idle, and animation state.
- Migrated the OSRS woodcutting script's input calls to `runtime.actions`.
- Local verification passes: `22 passed`; RemoteInput diagnostic help is available through `scripts/test_remote_input.py`.
- Live RemoteInput movement-only validation succeeded against RuneLite PID 26448: connected, healthy, and moved the virtual pointer to `(100, 100)` with elevated process access.
- Added structured vision adapters for template image matches and legacy outline objects.
- Added a runtime event bus; bot status, progress, log, and clear-log notifications now flow to UI controllers through runtime subscriptions.

### In progress: WindMouse and topology-zone foundations

- Added a transport-independent `generate_path` WindMouse implementation with bounded settings and deterministic test support.
- Made WindMouse the only mouse movement strategy; every generated point is delivered through the configured RemoteInput provider.
- Added configurable WindMouse parameters through `Mouse.set_windmouse_settings` and `Bot.configure_movement`.
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

Use WindMouse as the mandatory movement strategy. The algorithm calculates a path; the configured RemoteInput provider delivers that path to RuneLite.

The interface should support:

```python
mouse.move_to(point, speed="medium")
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

- Define interfaces for input, movement, screenshots, zones, colors, and detection. **Initial interfaces and compatibility adapters are complete.**
- Preserve current behavior through compatibility adapters where safe.
- Add mockable services and geometry tests.

### Phase 2 — RemoteInput and input modernization

- Inspect and select the official RemoteInput integration mechanism. **Complete: native DLL `ctypes` integration selected.**
- Add the input-provider interface. **Complete.**
- Implement the native RemoteInput adapter. **Complete for Windows x64 DLL exports used by mouse/keyboard actions.**
- Remove direct PyAutoGUI game actions from the production path. **Complete for all active bot scripts; remaining references are limited to non-input reads and commented legacy examples.**
- Add connection diagnostics and a mock provider. **Complete: mock provider, health check, movement-only diagnostic script, and UI PID validation.**
- Verify minimized/background RuneLite operation. **Complete: RemoteInput connected, passed health checks, and moved the virtual pointer while RuneLite was minimized; the client was restored and remained responsive.**

### Phase 3 — WindMouse

- Implement WindMouse independently of input transport. **Initial path generator complete.**
- Connect it to `RemoteInputProvider`. **Complete through the shared `Mouse` provider boundary.**
- Add configurable WindMouse settings.
- **WindMouse UI controls and typed runtime configuration persistence complete; broader UI validation remains pending.**
- **Superseded: movement strategy selection and desktop Bezier delivery were removed from production game actions.**

### Phase 4 — Zones and HSV vision

- Extract current `Window` rectangles into zone objects. **Initial `Window.zones` implementation complete.**
- Add coordinate transforms.
- **Complete for screen/zone-relative conversions.**
- Add exclusion/subtraction regions. **Initial masking support complete.**
- Add zone-scoped detection helpers. **HSV, template-image, legacy outline, and OCR detections share a structured result with zone and screen-bound metadata.**
- Add HSV profiles and masking. **Initial implementation and the OSRS Vision Debug profile editor are complete; broader integration remains intentionally script-specific.**
- Add point selection and structured detection results. **Complete for the current OSRS vision services, including confidence and zone/screen-bound metadata.**
- Add screenshot fixtures and vision tests. **Complete: deterministic and captured RuneLite fixture coverage are available.**

### Phase 5 — Runtime architecture

- Introduce the controller/service structure. **Initial lightweight `BotRuntime` and service facades complete.**
- Add sensor snapshots. **Normalized `SensorSnapshot`/`SensorService`, live StatusSocket wiring, and inventory/idle helpers are complete.**
- Move direct utility calls out of scripts where practical. **Initial action/vision paths are available; the woodcutter now uses structured HSV detections for tagged-tree discovery and runtime actions for interaction.**
- Support the current RuneLite layout. **The current captured layout is supported; additional layouts and resolutions are intentionally out of scope.**
- Decouple UI callbacks from bot implementation details. **Status, progress, logging, and clear-log updates use runtime events; controller subscriptions are released when the selected script changes.**

### Phase 6 — Script and UI migration

- Migrate one example script first, preferably mining or woodcutting. **Complete: woodcutter uses `runtime.actions` for input and `runtime.vision` with a named HSV tagged-tree profile.**
- Update remaining scripts incrementally. **All remaining OSRS scripts use the shared RemoteInput/WindMouse path and runtime sensor snapshots where applicable.**
- Add UI controls for RemoteInput, WindMouse settings, HSV profiles, and zone debugging. **RemoteInput/WindMouse controls and the OSRS Vision Debug panel are complete.**

### Phase 7 — Stabilization and documentation

- Add unit tests and screenshot-based regression tests. **Complete for the current OSRS fixture set.**
- Add RemoteInput setup and troubleshooting documentation.
- Add a native dependency/build guide. **Complete: `documentation/remote-input-build.md`.**
- Document the security, reliability, and account-risk limitations clearly.

## Success criteria

- No production bot action sends direct mouse or keyboard input through PyAutoGUI or equivalent desktop APIs.
- RuneLite can remain minimized while the bot operates through RemoteInput.
- Existing screenshots and vision utilities remain usable during migration.
- A migrated sample script uses controller services rather than low-level globals.
- Input, zones, colors, and detection can be tested without a live RuneLite session.
- RemoteInput failure prevents accidental fallback to direct game-client input.
