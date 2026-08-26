"""Guardrails around config selection.

The production config must refuse to boot without a real SECRET_KEY.
A known-public session-signing key would make every session cookie
and CSRF token forgeable.
"""
from __future__ import annotations

import pytest

from app.config import (
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    resolve_config,
)


def test_resolve_dev_returns_dev_config():
    assert resolve_config("development") is DevelopmentConfig


def test_resolve_testing_returns_testing_config():
    assert resolve_config("testing") is TestingConfig


def test_resolve_production_raises_without_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        resolve_config("production")


def test_resolve_production_raises_on_dev_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "dev-secret-change-me")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        resolve_config("production")


def test_resolve_production_succeeds_with_real_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    assert resolve_config("production") is ProductionConfig
