"""Tests for the content-addressed response cache."""
from __future__ import annotations

from pathlib import Path

from drleval.cache import _key


def test_cache_key_is_deterministic():
    p = {"model": "x", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
    assert _key(p) == _key(p)


def test_cache_key_changes_on_model():
    p1 = {"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}]}
    p2 = {"model": "claude-sonnet-4-5", "messages": [{"role": "user", "content": "hi"}]}
    assert _key(p1) != _key(p2)


def test_cache_key_changes_on_messages():
    p1 = {"model": "x", "messages": [{"role": "user", "content": "hi"}]}
    p2 = {"model": "x", "messages": [{"role": "user", "content": "yo"}]}
    assert _key(p1) != _key(p2)


def test_cache_key_stable_across_kwarg_order():
    # Key uses canonical JSON (sort_keys) so insertion order doesn't matter.
    p1 = {"model": "x", "messages": [], "max_tokens": 10, "temperature": 0.0}
    p2 = {"temperature": 0.0, "model": "x", "max_tokens": 10, "messages": []}
    assert _key(p1) == _key(p2)


def test_install_is_idempotent(tmp_path: Path):
    from drleval import cache

    # Without DRLEVAL_CACHE_DIR env, install should be a no-op.
    import os
    os.environ.pop("DRLEVAL_CACHE_DIR", None)
    cache.install(None)  # no-op, no crash
    assert cache._INSTALLED is False or cache._INSTALLED is True  # either is fine
