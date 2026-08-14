"""Deprecated import shim for the application-level structured-output service."""

from app.services.llm.structured_output import generate_structured

__all__ = ["generate_structured"]
