"""
tests/test_prod_preflight.py — Unit tests for production RAGAs preflight checks.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from evaluation.prod_preflight import (
    CorpusCounts,
    bootstrap_eval_env,
    fetch_corpus_counts,
    mask_database_url,
    run_preflight,
    validate_production_rds,
)


def test_mask_database_url_redacts_password() -> None:
    """Password portion of DATABASE_URL should not appear in masked output."""
    raw = "postgresql://postgres:secret@host.example.com:5432/permit_rag"
    masked = mask_database_url(raw)
    assert "secret" not in masked
    assert masked == "postgresql://postgres:***@host.example.com:5432/permit_rag"


def test_validate_production_rds_rejects_local_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local ENVIRONMENT should fail validation."""
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:pw@permit-rag-postgres.cilq6.us-east-1.rds.amazonaws.com:5432/permit_rag",
    )
    errors = validate_production_rds()
    assert any("ENVIRONMENT=production" in err for err in errors)


def test_validate_production_rds_rejects_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """Localhost DATABASE_URL should fail validation."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:pw@localhost:5432/permit_rag")
    errors = validate_production_rds()
    assert any("localhost" in err for err in errors)


def test_fetch_corpus_counts_reads_dict_rows() -> None:
    """Counts should be read from dict-row query results."""
    conn = MagicMock()
    conn.execute.side_effect = [
        SimpleNamespace(fetchone=lambda: {"n": 10}),
        SimpleNamespace(fetchone=lambda: {"n": 9}),
        SimpleNamespace(fetchone=lambda: {"n": 7170}),
        SimpleNamespace(fetchone=lambda: {"n": 7170}),
    ]
    counts = fetch_corpus_counts(conn)
    assert counts == CorpusCounts(
        documents=10,
        active_documents=9,
        chunks=7170,
        embedded_chunks=7170,
    )


def test_run_preflight_fails_when_corpus_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty corpus should fail preflight even when RDS settings are valid."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:pw@permit-rag-postgres.cilq6.us-east-1.rds.amazonaws.com:5432/permit_rag",
    )

    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_conn
    mock_cm.__exit__.return_value = False

    with patch("evaluation.prod_preflight.bootstrap_eval_env", return_value="production"), patch(
        "db.client.get_conn",
        return_value=mock_cm,
    ), patch(
        "evaluation.prod_preflight.fetch_corpus_counts",
        return_value=CorpusCounts(
            documents=0,
            active_documents=0,
            chunks=0,
            embedded_chunks=0,
        ),
    ):
        result = run_preflight()

    assert result.ok is False
    assert any("FAIL: active documents" in line for line in result.messages)


def test_run_preflight_passes_when_corpus_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-empty active docs and embeddings should pass preflight."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:pw@permit-rag-postgres.cilq6.us-east-1.rds.amazonaws.com:5432/permit_rag",
    )

    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_conn
    mock_cm.__exit__.return_value = False

    with patch("evaluation.prod_preflight.bootstrap_eval_env", return_value="production"), patch(
        "db.client.get_conn",
        return_value=mock_cm,
    ), patch(
        "evaluation.prod_preflight.fetch_corpus_counts",
        return_value=CorpusCounts(
            documents=10,
            active_documents=10,
            chunks=7170,
            embedded_chunks=7170,
        ),
    ):
        result = run_preflight()

    assert result.ok is True
    assert any("PASS: production corpus is ready" in line for line in result.messages)


def test_bootstrap_eval_env_uses_production_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit ENVIRONMENT=production should resolve to production profile."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    def _fake_load_dotenv(path: Path, override: bool = False) -> bool:
        if Path(path).name == ".env":
            os.environ["DATABASE_URL"] = "postgresql://x:y@host/db"
        return True

    with patch("evaluation.prod_preflight.load_dotenv", side_effect=_fake_load_dotenv):
        profile = bootstrap_eval_env()

    assert profile == "production"
    assert os.environ.get("DATABASE_URL") == "postgresql://x:y@host/db"
