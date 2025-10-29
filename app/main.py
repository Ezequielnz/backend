"""
Compatibility module exposing the FastAPI application for tests and ASGI runners.

Pytest suites import `app.main:app`, but the project-level entrypoint currently
lives in the top-level `main.py`.  Re-exporting the instantiated FastAPI app
from here keeps that import path stable without duplicating startup logic.
"""

from main import app  # type: ignore F401

__all__ = ["app"]
