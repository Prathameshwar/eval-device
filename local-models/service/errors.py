"""Stable public errors; native exceptions and credentials never become log messages."""


class ManagerError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def require(condition, code, message, status=400):
    if not condition:
        raise ManagerError(code, message, status)
