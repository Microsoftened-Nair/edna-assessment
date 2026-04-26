"""REST API surface for embeddings-only DNABERT2 runs."""

from .server import create_app

__all__ = ["create_app"]
