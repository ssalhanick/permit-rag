"""
tests/test_load_env.py — Environment bootstrap tests
"""

from __future__ import annotations

import os

from load_env import bootstrap_env, resolve_environment


def test_resolve_environment_defaults_to_local(monkeypatch) -> None:
    """Laptop dev should default to local when ENVIRONMENT is unset."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
    monkeypatch.delenv("ECS_CONTAINER_METADATA_URI_V4", raising=False)
    assert resolve_environment() == "local"


def test_resolve_environment_ecs_is_production(monkeypatch) -> None:
    """ECS tasks should resolve to production without dotenv files."""
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")
    assert resolve_environment() == "production"


def test_bootstrap_env_loads_local_profile(monkeypatch, tmp_path) -> None:
    """bootstrap_env should load .env.local then .env secrets."""
    for key in ("DATABASE_URL", "ANTHROPIC_API_KEY", "ENVIRONMENT", "AWS_EXECUTION_ENV"):
        monkeypatch.delenv(key, raising=False)

    (tmp_path / ".env.local").write_text("DATABASE_URL=postgresql://local/test\n")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-test\n")

    import load_env as mod

    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    profile = mod.bootstrap_env()
    assert profile == "local"
    assert os.environ["DATABASE_URL"] == "postgresql://local/test"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test"
