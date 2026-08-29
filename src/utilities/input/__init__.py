"""Input providers used by OSBC bot actions.

Game-client input must be routed through :class:`InputProvider`.  The
RemoteInput provider is intentionally fail-closed until its native extension
is installed and attached to a Java client.
"""

from .provider import (
    InputProvider,
    InputProviderError,
    MockInputProvider,
    RemoteInputProvider,
)

__all__ = [
    "InputProvider",
    "InputProviderError",
    "MockInputProvider",
    "RemoteInputProvider",
]
