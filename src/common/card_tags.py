"""Shared helpers for the generated card-function table."""
from __future__ import annotations


def is_card_key(key) -> bool:
    """Return whether a JSON key is a card id rather than reserved metadata."""

    return str(key).lstrip("-").isdigit()


__all__ = ["is_card_key"]
