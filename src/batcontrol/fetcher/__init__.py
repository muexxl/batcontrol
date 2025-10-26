"""Fetcher Module

This module provides utilities for fetching data from external APIs:
- RelaxedCaching: Thread-safe caching with TTL support
- HTTP request utilities (coming soon)
"""

from .relaxed_caching import RelaxedCaching, CacheMissError

__all__ = ['RelaxedCaching', 'CacheMissError']
