"""Small per-process protection; deployment ingress enforces shared replica limits."""

from collections import OrderedDict
from time import monotonic


class RateLimiter:
    def __init__(self, max_keys=10000):
        self.entries = OrderedDict()
        self.max_keys = max_keys

    def allow(self, key, limit, seconds=60):
        timestamp = monotonic()
        start, count = self.entries.pop(key, (timestamp, 0))
        if timestamp - start >= seconds:
            start, count = timestamp, 0
        self.entries[key] = (start, count + 1)
        while len(self.entries) > self.max_keys:
            self.entries.popitem(last=False)
        return count < limit
