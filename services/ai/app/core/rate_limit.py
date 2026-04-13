"""Shared rate limiter instance.

Import from here to ensure a single Limiter is used across the application.
Avoids creating multiple independent rate limit counters.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
