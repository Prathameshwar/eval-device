"""One boot identity and ordered heartbeat numbers for all work in this process."""

import threading
from itertools import count
from uuid import uuid4

_boot = str(uuid4())
_sequence = count()
_lock = threading.Lock()


def heartbeat(configuration=None, *, capabilities=None):
    with _lock:
        body = {"boot_id": _boot, "sequence_number": next(_sequence)}
    if configuration:
        body.update(
            applied_profile_revision_id=configuration["profile_revision_id"],
            applied_configuration_hash=configuration["configuration_hash"],
        )
    if capabilities is not None:
        body["capabilities"] = capabilities
    return body
