"""REST API surface for the Deep-Sea eDNA pipeline."""

from .server import create_app

__all__ = ["create_app"]
