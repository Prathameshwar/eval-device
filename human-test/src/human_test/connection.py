"""Desktop connection-file location; pairing logic lives in training-client."""

from pathlib import Path

from training_client.connection import (
    DEFAULT_PLATFORM as DEFAULT_PLATFORM,
)
from training_client.connection import (
    ERRORS as ERRORS,
)
from training_client.connection import (
    ConnectionError as ConnectionError,
)
from training_client.connection import (
    PairingClient as Client,
)
from training_client.connection import (
    connection_values as connection_values,
)
from training_client.connection import (
    platform_origin as platform_origin,
)
from training_client.connection import (
    read_connection as _read,
)
from training_client.connection import (
    save_connection as _save,
)

CONNECTION_FILE = Path(__file__).resolve().parents[2] / ".local/platform-connection/connection.json"


def read_connection(path=CONNECTION_FILE):
    return _read(path)


def save_connection(data, path=CONNECTION_FILE):
    return _save(data, path)


class PairingClient(Client):
    def __init__(self, origin, *, transport=None, path=CONNECTION_FILE):
        super().__init__(origin, transport=transport, path=path)
