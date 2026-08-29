from utilities.input import InputProviderError, MockInputProvider, RemoteInputProvider


class FakeNativeFunction:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class FakeRemoteInputLibrary:
    def __init__(self):
        self.EIOS_RequestTarget = FakeNativeFunction(1234)
        self.EIOS_Inject_PID = FakeNativeFunction()
        self.EIOS_ReleaseTarget = FakeNativeFunction()
        self.EIOS_MoveMouse = FakeNativeFunction()
        self.EIOS_HoldMouse = FakeNativeFunction()
        self.EIOS_ReleaseMouse = FakeNativeFunction()
        self.EIOS_HoldKey = FakeNativeFunction()
        self.EIOS_ReleaseKey = FakeNativeFunction()
        self.EIOS_GetTargetDimensions = FakeNativeFunction()


def test_mock_provider_records_events():
    provider = MockInputProvider()
    provider.connect()
    provider.move_to(10, 20)
    provider.click()
    provider.key_down("shift")
    provider.key_up("shift")

    assert [event.name for event in provider.events] == [
        "connect",
        "move_to",
        "mouse_down",
        "mouse_up",
        "key_down",
        "key_up",
    ]
    assert provider.events[1].args == (10, 20)


def test_mock_provider_requires_connection():
    provider = MockInputProvider()

    try:
        provider.click()
    except InputProviderError:
        pass
    else:
        raise AssertionError("Disconnected provider accepted an event")


def test_remote_input_fails_closed():
    provider = RemoteInputProvider()

    try:
        provider.connect()
    except InputProviderError as error:
        assert "fallback is disabled" in str(error)
    else:
        raise AssertionError("Unconfigured RemoteInput unexpectedly connected")


def test_remote_input_uses_native_eios_api(tmp_path):
    dll_path = tmp_path / "libRemoteInput-x86_64.dll"
    dll_path.touch()
    library = FakeRemoteInputLibrary()
    provider = RemoteInputProvider(process_id=9876, dll_path=dll_path, library_loader=lambda _: library)

    provider.connect()
    provider.move_to(10, 20)
    provider.mouse_down("right")
    provider.mouse_up("right")
    provider.key_down("shift")
    provider.key_up("shift")
    provider.disconnect()

    assert library.EIOS_RequestTarget.calls == [(b"9876",)]
    assert library.EIOS_Inject_PID.calls == [(9876,)]
    assert library.EIOS_MoveMouse.calls[0][1:] == (10, 20)
    assert library.EIOS_HoldMouse.calls[0][1:] == (0, 0, 0)
    assert library.EIOS_ReleaseMouse.calls[0][1:] == (0, 0, 0)
    assert library.EIOS_HoldKey.calls[0][1:] == (0x10,)
    assert library.EIOS_ReleaseKey.calls[0][1:] == (0x10,)
    assert library.EIOS_ReleaseTarget.calls
