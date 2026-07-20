"""
tests/test_kickoff_chat.py — Tests for conversational project kickoff chat.
"""

from __future__ import annotations

import json
from typing import Any
from fastapi.testclient import TestClient
from api.main import app


def test_parse_json_response() -> None:
    """It should parse raw JSON or JSON enclosed in markdown blocks."""
    from rag.generator import _parse_json_response

    raw_json = '{"is_complete": true, "persona": "diy"}'
    parsed = _parse_json_response(raw_json)
    assert parsed["is_complete"] is True
    assert parsed["persona"] == "diy"

    markdown_json = '```json\n{"is_complete": false, "next_question": "how?"}\n```'
    parsed_md = _parse_json_response(markdown_json)
    assert parsed_md["is_complete"] is False
    assert parsed_md["next_question"] == "how?"


def test_generate_kickoff_chat_response_ollama(monkeypatch) -> None:
    """It should parse Ollama chat responses correctly."""
    import rag.generator as generator_module

    class DummyCapabilities:
        supports_local_runtime = True
        supports_prompt_caching = False
        provider = "ollama"

    monkeypatch.setattr(
        generator_module,
        "get_provider_capabilities",
        lambda: DummyCapabilities(),
    )

    class DummyResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "message": {
                    "content": '{"is_complete": true, "persona": "contractor", "budget": "$100k"}'
                }
            }

    import requests
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: DummyResponse())

    res = generator_module.generate_kickoff_chat_response(
        [{"role": "user", "content": "I am a contractor with 100k budget"}],
        address="123 Dallas St",
        municipality="Dallas",
        spaces=["Kitchen"],
        work_types=["Plumbing"],
    )
    assert res["is_complete"] is True
    assert res["persona"] == "contractor"
    assert res["budget"] == "$100k"


def test_kickoff_chat_route_endpoint(monkeypatch) -> None:
    """The /projects/kickoff/chat endpoint should call generator and return response."""
    import rag.generator as generator_module

    def dummy_generate(history: list[dict], **kwargs: Any) -> dict[str, Any]:
        return {
            "is_complete": True,
            "persona": "diy",
            "budget": "$10k",
            "custom_system_prompt": "DIY guide",
        }

    monkeypatch.setattr(
        generator_module,
        "generate_kickoff_chat_response",
        dummy_generate,
    )

    # Mock Cognito Auth dependency
    from api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "00000000-0000-0000-0000-000000000000", "role": "owner"}

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/projects/kickoff/chat",
            json={
                "history": [{"role": "user", "content": "hello"}],
                "address": "Dallas",
            },
            headers={"Authorization": "Bearer dummy_token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_complete"] is True
        assert body["persona"] == "diy"
        assert body["budget"] == "$10k"
        assert body["custom_system_prompt"] == "DIY guide"
    finally:
        app.dependency_overrides.clear()
