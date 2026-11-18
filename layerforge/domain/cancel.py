"""Cooperative cancellation shared by long-running domain and infrastructure work."""


class Cancelled(Exception):
    """Raised inside a background task when its cancel token is set."""
