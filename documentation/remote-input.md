# RemoteInput setup

OSBC uses Brandon-T's native RemoteInput DLL directly through `ctypes`. It does not use
`PostMessage`, PyAutoGUI, or a desktop-input fallback for game-client actions.

Place the 64-bit Windows release binary at the project root as
`libRemoteInput-x86_64.dll`, or pass its path explicitly when creating the provider.
RemoteInput injects into the RuneLite Java process, so pass the Java process ID rather than
the RuneLite launcher process ID:

```python
from utilities.input import RemoteInputProvider

provider = RemoteInputProvider(process_id=JAVA_PROCESS_ID)
provider.connect()
assert provider.health_check()
provider.move_to(300, 250)  # RuneLite canvas-relative coordinates
provider.click()
provider.disconnect()
```

The provider calls the DLL's `EIOS_Inject_PID`, `EIOS_RequestTarget`, `EIOS_MoveMouse`,
`EIOS_HoldMouse`, `EIOS_ReleaseMouse`, `EIOS_HoldKey`, and `EIOS_ReleaseKey` exports.
If attaching fails, it raises `InputProviderError` and no desktop-input fallback is used.
On Windows, OSBC and RuneLite may need to run at the same elevation level. If the diagnostic
reports `Cannot Initialize Maps`, retry it from an elevated terminal.

For a safe connection test (movement only; no click or keyboard input), run:

```powershell
.\.venv\Scripts\python.exe scripts\test_remote_input.py 33168
```

## Using RemoteInput from the OSBC UI

Enter RuneLite's Java process ID in the **RemoteInput PID** field in the bot
controls, then press **Play**. OSBC saves the PID locally and injects/attaches
RemoteInput before a script starts. A missing or invalid PID prevents startup;
desktop mouse and keyboard input are not used as a fallback.
