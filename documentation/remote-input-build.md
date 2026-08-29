# RemoteInput native dependency

OSBC requires the 64-bit Windows RemoteInput library:
`libRemoteInput-x86_64.dll`.

Place the x64 DLL at the repository root, or select an explicit DLL path in
the OSBC controls. The Python process, RuneLite Java process, and DLL must all
have the same architecture. A 32-bit DLL cannot be loaded by the supported
64-bit Python environment.

The provider expects these native exports:

- `EIOS_Inject_PID`
- `EIOS_RequestTarget`
- `EIOS_MoveMouse`
- `EIOS_HoldMouse` / `EIOS_ReleaseMouse`
- `EIOS_HoldKey` / `EIOS_ReleaseKey`

If building from RemoteInput source, build its x64 Windows release target and
copy the resulting DLL without renaming its exported functions. Install the
matching Microsoft Visual C++ x64 runtime if Windows reports a missing runtime
DLL.

Run the non-invasive validator against every registered OSRS script:

```powershell
.\.venv\Scripts\python.exe scripts\validate_osrs_scripts.py --pid <RuneLite-Java-PID>
```

The validator performs only a RemoteInput connect and health check. It never
starts a bot loop or sends a click or key. Omit `--pid` for an offline mock
provider check.
