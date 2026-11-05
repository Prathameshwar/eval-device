"""Read-only availability monitoring; no service ownership or recovery."""

import time
from dataclasses import dataclass

import httpx
from startup import StopRequested, message


@dataclass
class Service:
    name: str
    check: object
    bad_checks: int = 0


class Supervisor:
    def __init__(self, state=lambda *a: None):
        self.state = state
        self.services = []
        self.cancelled = None
        self.next_health = 0.0

    def watch(self, name, check):
        self.services.append(Service(name, check))

    def monitor(self):
        if self.cancelled and self.cancelled():
            raise StopRequested()
        if time.monotonic() < self.next_health:
            return
        self.next_health = time.monotonic() + 15
        for item in self.services:
            try:
                healthy = item.check()
            except (OSError, httpx.HTTPError):
                healthy = False
            if healthy:
                if item.bad_checks:
                    message("READY", f"{item.name}: availability recovered")
                item.bad_checks = 0
            else:
                item.bad_checks += 1
                message("WARN", f"{item.name}: availability check {item.bad_checks}/3 failed")
                if item.bad_checks >= 3:
                    raise RuntimeError(f"{item.name} remains unavailable; check its owner application")
        degraded = next((item.name for item in self.services if item.bad_checks), None)
        self.state("degraded" if degraded else "ready", degraded)
