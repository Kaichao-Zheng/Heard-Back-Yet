"""Discoverable ASGI entry point for the HeardBackYet web application."""

from heardbackyet.presentation.app import app, create_app

__all__ = ["app", "create_app"]
